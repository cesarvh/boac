"""
Copyright ©2019. The Regents of the University of California (Regents). All Rights Reserved.

Permission to use, copy, modify, and distribute this software and its documentation
for educational, research, and not-for-profit purposes, without fee and without a
signed licensing agreement, is hereby granted, provided that the above copyright
notice, this paragraph and the following two paragraphs appear in all copies,
modifications, and distributions.

Contact The Office of Technology Licensing, UC Berkeley, 2150 Shattuck Avenue,
Suite 510, Berkeley, CA 94720-1620, (510) 643-7201, otl@berkeley.edu,
http://ipira.berkeley.edu/industry-info for commercial licensing opportunities.

IN NO EVENT SHALL REGENTS BE LIABLE TO ANY PARTY FOR DIRECT, INDIRECT, SPECIAL,
INCIDENTAL, OR CONSEQUENTIAL DAMAGES, INCLUDING LOST PROFITS, ARISING OUT OF
THE USE OF THIS SOFTWARE AND ITS DOCUMENTATION, EVEN IF REGENTS HAS BEEN ADVISED
OF THE POSSIBILITY OF SUCH DAMAGE.

REGENTS SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. THE
SOFTWARE AND ACCOMPANYING DOCUMENTATION, IF ANY, PROVIDED HEREUNDER IS PROVIDED
"AS IS". REGENTS HAS NO OBLIGATION TO PROVIDE MAINTENANCE, SUPPORT, UPDATES,
ENHANCEMENTS, OR MODIFICATIONS.
"""

from datetime import datetime
from time import sleep

from boac.models.authorized_user import AuthorizedUser
from boac.models.cohort_filter import CohortFilter
from boac.models.curated_group import CuratedGroup
from boac.models.note import Note
from boac.models.note_attachment import NoteAttachment
from boac.models.note_read import NoteRead
import pytest
import simplejson as json
from tests.test_api.api_test_utils import all_cohorts_owned_by
from tests.util import mock_advising_note_s3_bucket, mock_legacy_note_attachment

asc_advisor_uid = '6446'
coe_advisor_uid = '1133399'
l_s_major_advisor_uid = '242881'
admin_uid = '2040'

coe_student = {
    'sid': '9000000000',
    'uid': '300847',
}


@pytest.fixture()
def mock_coe_advising_note():
    return Note.create(
        author_uid=coe_advisor_uid,
        author_name='Balloon Man',
        author_role='Spherical',
        author_dept_codes='COENG',
        sid=coe_student['sid'],
        subject='I was walking up Sixth Avenue',
        body='He spattered me with tomatoes, Hummus, chick peas',
    )


@pytest.fixture()
def mock_asc_advising_note(app, db):
    return Note.create(
        author_uid='1133399',
        author_name='Roberta Joan Anderson',
        author_role='Advisor',
        author_dept_codes=['COENG'],
        sid='3456789012',
        subject='The hissing of summer lawns',
        body="""
            She could see the valley barbecues from her window sill.
            See the blue pools in the squinting sun. Hear the hissing of summer lawns
        """,
        topics=['darkness', 'no color no contrast'],
    )


class TestGetNote:

    @classmethod
    def _api_note_by_id(cls, client, note_id, expected_status_code=200):
        response = client.get(f'/api/note/{note_id}')
        assert response.status_code == expected_status_code
        return response.json

    def test_not_authenticated(self, app, client, mock_coe_advising_note):
        """Returns 401 if not authenticated."""
        self._api_note_by_id(client=client, note_id=mock_coe_advising_note.id, expected_status_code=401)

    def test_get_note_by_id(self, app, client, fake_auth, mock_coe_advising_note):
        """Returns note in JSON compatible with BOA front-end."""
        fake_auth.login(coe_advisor_uid)
        note = self._api_note_by_id(client=client, note_id=mock_coe_advising_note.id)
        assert note
        assert 'id' in note
        assert note['type'] == 'note'
        assert note['body'] == note['message']
        assert note['read'] is False
        # Mark as read and re-test
        NoteRead.find_or_create(AuthorizedUser.get_id_per_uid(coe_advisor_uid), note['id'])
        assert self._api_note_by_id(client=client, note_id=mock_coe_advising_note.id)['read'] is True


class TestNoteCreation:

    def test_not_authenticated(self, app, client):
        """Returns 401 if not authenticated."""
        assert _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject='Rusholme Ruffians',
            body='This is the last night of the fair, And the grease in the hair',
            expected_status_code=401,
        )

    def test_admin_user_is_not_authorized(self, app, client, fake_auth):
        """Returns 401 if user is an admin."""
        fake_auth.login(admin_uid)
        admin = AuthorizedUser.find_by_uid(admin_uid)
        assert _api_note_create(
            app,
            client,
            author_id=admin.id,
            sid=coe_student['sid'],
            subject='Rusholme Ruffians',
            body='This is the last night of the fair, And the grease in the hair',
            expected_status_code=403,
        )

    def test_create_note(self, app, client, fake_auth):
        """Create a note."""
        fake_auth.login(coe_advisor_uid)
        subject = 'Vicar in a Tutu'
        new_note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject=subject,
            body='A scanty bit of a thing with a decorative ring',
        )
        note_id = new_note.get('id')
        assert new_note['read'] is True
        assert isinstance(note_id, int) and note_id > 0
        assert new_note['author']['uid'] == coe_advisor_uid
        assert 'name' in new_note['author']
        assert new_note['author']['role'] == 'Advisor'
        assert new_note['author']['departments'][0]['name'] == 'College of Engineering'
        assert new_note['updatedAt'] is None
        # Get notes per SID and compare
        notes = _get_notes(client, coe_student['uid'])
        match = next((n for n in notes if n['id'] == note_id), None)
        assert match and match['subject'] == subject

    def test_create_note_prefers_ldap_dept_affiliation_and_title(self, app, client, fake_auth):
        fake_auth.login(l_s_major_advisor_uid)
        new_note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(l_s_major_advisor_uid),
            sid=coe_student['sid'],
            subject='A dreaded sunny day',
            body='Keats and Yeats are on your side',
        )
        assert new_note['author']['departments'][0]['name'] == 'Department of English'
        assert new_note['author']['role'] == 'Harmless Drudge'

    def test_updated_date_is_none_when_note_create(self, app, client, fake_auth):
        """Create a note and expect none updated_at."""
        fake_auth.login(coe_advisor_uid)
        note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject='Creating is not updating',
            body=None,
        )
        assert note['createdAt'] is not None
        assert note['updatedAt'] is None

    def test_create_note_with_topics(self, app, client, fake_auth):
        """Create a note with topics."""
        fake_auth.login(coe_advisor_uid)
        note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject='Incubate transparent web services',
            body='Facilitate value-added initiatives',
            topics=['collaborative synergies', 'integrated architectures', 'vertical solutions'],
        )
        assert len(note.get('topics')) == 3
        assert note.get('topics')[0] == 'Collaborative Synergies'
        assert note.get('topics')[1] == 'Integrated Architectures'
        assert note.get('topics')[2] == 'Vertical Solutions'
        assert note['createdAt'] is not None
        assert note['updatedAt'] is None

    def test_create_note_with_raw_url_in_body(self, app, client, fake_auth):
        """Create a note with topics."""
        fake_auth.login(coe_advisor_uid)
        note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject='Get rich quick',
            body='Get an online degree at send.money.edu university',
        )
        expected_body = 'Get an online degree at <a href="http://send.money.edu" target="_blank">send.money.edu</a> university'
        assert note.get('body') == expected_body
        assert note['createdAt'] is not None
        assert note['updatedAt'] is None

    def test_create_note_with_attachments(self, app, client, fake_auth, mock_note_template):
        """Create a note, with two attachments."""
        fake_auth.login(coe_advisor_uid)
        base_dir = app.config['BASE_DIR']
        note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject='I come with attachments',
            body='I come correct',
            attachments=[
                f'{base_dir}/fixtures/mock_advising_note_attachment_1.txt',
                f'{base_dir}/fixtures/mock_advising_note_attachment_2.txt',
            ],
            template_attachment_ids=list(map(lambda a: a.id, mock_note_template.attachments)),
        )
        template_attachment_count = len(mock_note_template.attachments)
        assert template_attachment_count
        expected_attachment_count = template_attachment_count + 2

        assert len(note.get('attachments')) == expected_attachment_count
        assert note['createdAt'] is not None
        assert note['updatedAt'] is None


class TestBatchNoteCreation:

    def test_batch_note_creation_with_sids(self, app, client, fake_auth, mock_note_template):
        """Batch note creation with list of SIDs."""
        fake_auth.login(coe_advisor_uid)
        base_dir = app.config['BASE_DIR']
        advisor = AuthorizedUser.find_by_uid(coe_advisor_uid)
        subject = f'Elevate Me Later {datetime.now().timestamp()}'
        sids = [
            '960759268', '856024035', '370048698', '709706581', '518777297', '912902626', '466030628', '695508833',
            '729680066', '534614253', '329221239', '882981218', '734373851', '968319871', '824231751', '904338427',
            '849739234', '310798157', '301806363', '352212185', '3456789012', '5678901234', '11667051', '8901234567',
            '3456789012', '11667051',
        ]
        # Curated group
        curated_group_ids, sids_in_curated_groups = _get_curated_groups_ids_and_sids(advisor)
        # We need at least one curated_group SID that is NOT in the list o' sids above.
        sid_expected_in_curated_group = '7890123456'
        assert sid_expected_in_curated_group in sids_in_curated_groups
        assert sid_expected_in_curated_group not in sids
        # Cohort
        cohort_ids, sids_in_cohorts = _get_cohorts_ids_and_sids(advisor)
        # We need at least one cohort SID that is NOT in the list o' sids above.
        expected_sid_in_cohort = '9000000000'
        assert expected_sid_in_cohort not in sids
        assert expected_sid_in_cohort in sids_in_cohorts

        # List above has duplicates - verify that it is de-duped.
        distinct_sids = set(sids + sids_in_curated_groups + sids_in_cohorts)
        topics = ['Slanted', 'Enchanted']
        _api_batch_note_create(
            app,
            client,
            author_id=advisor.id,
            subject=subject,
            body='Well you greet the tokens and stamps, beneath the fake oil burnin\' lamps',
            sids=sids,
            curated_group_ids=curated_group_ids,
            cohort_ids=cohort_ids,
            topics=topics,
            attachments=[
                f'{base_dir}/fixtures/mock_advising_note_attachment_1.txt',
                f'{base_dir}/fixtures/mock_advising_note_attachment_2.txt',
            ],
            template_attachment_ids=list(map(lambda a: a.id, mock_note_template.attachments)),
        )
        notes = Note.query.filter(Note.subject == subject).all()
        assert len(notes) == len(distinct_sids)
        matching_notes_read = NoteRead.get_notes_read_by_user(viewer_id=advisor.id, note_ids=[str(n.id) for n in notes])
        assert len(notes) == len(matching_notes_read)

        template_attachment_count = len(mock_note_template.attachments)
        assert template_attachment_count
        expected_attachment_count = template_attachment_count + 2

        for sid in distinct_sids:
            note = next((n for n in notes if n.sid == sid), None)
            assert note
            assert note.subject == subject
            assert note.author_uid == advisor.uid
            assert len(note.topics) == 2
            topics = [t.topic for t in note.topics]
            assert 'Slanted' in topics
            assert 'Enchanted' in topics
            assert len(note.attachments) == expected_attachment_count

    def test_batch_student_count_not_authenticated(self, client):
        """Deny anonymous access to batch note metadata."""
        _api_batch_distinct_student_count(client, sids=['11667051'], cohort_ids=[1, 2], expected_status_code=401)

    def test_batch_student_count_not_owner(self, client, fake_auth):
        """Deny user access to cohort owned by some other dept."""
        user_id = AuthorizedUser.get_id_per_uid(coe_advisor_uid)
        cohorts = CohortFilter.get_cohorts_of_user_id(user_id)
        # Assert non-zero student count
        assert sum(list(map(lambda c: c['totalStudentCount'], cohorts)))
        # Log in as non-owner
        fake_auth.login(asc_advisor_uid)
        count = _api_batch_distinct_student_count(client, cohort_ids=[c['id'] for c in cohorts])
        assert count == 0

    def test_batch_student_count(self, client, fake_auth):
        """Get distinct number of SIDs in union of cohorts, curated groups, etc."""
        user_id = AuthorizedUser.get_id_per_uid(coe_advisor_uid)
        cohort_ids = []
        sids = set()
        for cohort in CohortFilter.get_cohorts_of_user_id(user_id):
            cohort_id = cohort['id']
            cohort_ids.append(cohort_id)
            sids.update(set(CohortFilter.get_sids(cohort_id)))

        assert len(sids) > 1
        curated_group = CuratedGroup.create(user_id, 'Like a lemon to a lime, a lime to a lemon')
        curated_group_ids = [curated_group.id]
        # We use SIDs from cohorts (above). Therefore, we expect no increase in 'batch_distinct_student_count'.
        for sid in sids:
            CuratedGroup.add_student(curated_group.id, sid)
        # A specific student (SID) that is in neither cohorts nor curated groups.
        some_other_sid = '5678901234'
        assert some_other_sid not in sids
        # Log in as authorized user
        fake_auth.login(coe_advisor_uid)
        count = _api_batch_distinct_student_count(
            client,
            cohort_ids=cohort_ids,
            curated_group_ids=curated_group_ids,
            sids=[some_other_sid],
        )
        assert len(sids) + 1 == count


class TestNoteTopics:

    @classmethod
    def _api_all_note_topics(cls, client, include_deleted=None, expected_status_code=200):
        api_path = '/api/notes/topics'
        if include_deleted is not None:
            api_path += f'?includeDeleted={str(include_deleted).lower()}'
        response = client.get(api_path)
        assert response.status_code == expected_status_code
        return response.json

    def test_get_all_topics_not_authenticated(self, client):
        """Deny anonymous access to note topics."""
        self._api_all_note_topics(client, expected_status_code=401)

    def test_get_all_topics_including_deleted(self, client, fake_auth):
        """Get all note topic options, including deleted."""
        fake_auth.login(coe_advisor_uid)
        api_json = self._api_all_note_topics(client, include_deleted=True)
        assert 'Topic 1' in api_json
        assert 'I am a deleted topic' in api_json

    def test_get_all_topics(self, client, fake_auth):
        """Get all note topic options, not including deleted."""
        fake_auth.login(coe_advisor_uid)
        api_json = self._api_all_note_topics(client)
        assert 'Topic 1' in api_json
        assert 'I am a deleted topic' not in api_json


class TestNoteAttachments:

    def test_remove_attachment(self, app, client, fake_auth):
        """Remove an attachment from an existing note."""
        fake_auth.login(coe_advisor_uid)
        base_dir = app.config['BASE_DIR']
        note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject='I come with attachments',
            body='I come correct',
            attachments=[
                f'{base_dir}/fixtures/mock_advising_note_attachment_1.txt',
                f'{base_dir}/fixtures/mock_advising_note_attachment_2.txt',
            ],
        )
        assert note['updatedAt'] is None
        # Pause one second to ensure a distinct updatedAt.
        sleep(1)
        note_id = note['id']
        id_to_delete = note['attachments'][0]['id']
        id_to_keep = note['attachments'][1]['id']
        delete_response = client.delete(f'/api/notes/{note_id}/attachment/{id_to_delete}')
        assert delete_response.status_code == 200
        assert len(delete_response.json['attachments']) == 1
        assert delete_response.json['attachments'][0]['filename'] == 'mock_advising_note_attachment_2.txt'
        notes = _get_notes(client, coe_student['uid'])
        match = next((n for n in notes if n['id'] == note_id), None)
        assert len(match.get('attachments')) == 1
        assert match['attachments'][0]['id'] == id_to_keep
        assert match['attachments'][0]['filename'] == 'mock_advising_note_attachment_2.txt'
        assert match['updatedAt'] is not None

    def test_add_attachment(self, app, client, fake_auth):
        """Add an attachment to an existing note."""
        fake_auth.login(coe_advisor_uid)
        base_dir = app.config['BASE_DIR']
        note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject='No attachments yet',
            body='I travel light',
        )
        assert note['updatedAt'] is None
        # Pause one second to ensure a distinct updatedAt.
        sleep(1)
        note_id = note['id']
        with mock_advising_note_s3_bucket(app):
            data = {'attachment[0]': open(f'{base_dir}/fixtures/mock_advising_note_attachment_1.txt', 'rb')}
            response = client.post(
                f'/api/notes/{note_id}/attachment',
                buffered=True,
                content_type='multipart/form-data',
                data=data,
            )
        assert response.status_code == 200
        updated_note = response.json
        assert len(updated_note['attachments']) == 1
        assert updated_note['attachments'][0]['filename'] == 'mock_advising_note_attachment_1.txt'
        assert updated_note['updatedAt'] is not None


class TestMarkNoteRead:

    def test_mark_read_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        assert client.post('/api/notes/11667051-00001/mark_read').status_code == 401

    def test_mark_note_read(self, app, client, fake_auth):
        """Marks a note as read."""
        fake_auth.login(coe_advisor_uid)
        all_notes_unread = _get_notes(client, 61889)
        assert len(all_notes_unread) == 7
        for note in all_notes_unread:
            assert note['read'] is False

        # SIS notes
        response = client.post('/api/notes/11667051-00001/mark_read')
        assert response.status_code == 201
        response = client.post(f'/api/notes/11667051-00003/mark_read')
        assert response.status_code == 201
        # ASC note
        response = client.post('/api/notes/11667051-139379/mark_read')
        assert response.status_code == 201
        # E&I note
        response = client.post('/api/notes/11667051-151620/mark_read')
        assert response.status_code == 201

        all_notes_after_read = _get_notes(client, 61889)
        assert len(all_notes_after_read) == 7
        assert all_notes_after_read[0]['id'] == '11667051-00001'
        assert all_notes_after_read[0]['read'] is True
        assert all_notes_after_read[1]['id'] == '11667051-00002'
        assert all_notes_after_read[1]['read'] is False
        assert all_notes_after_read[2]['id'] == '11667051-00003'
        assert all_notes_after_read[2]['read'] is True
        assert all_notes_after_read[3]['id'] == '11667051-00004'
        assert all_notes_after_read[3]['read'] is False
        assert all_notes_after_read[4]['id'] == '11667051-139362'
        assert all_notes_after_read[4]['read'] is False
        assert all_notes_after_read[5]['id'] == '11667051-139379'
        assert all_notes_after_read[5]['read'] is True
        assert all_notes_after_read[6]['id'] == '11667051-151620'
        assert all_notes_after_read[6]['read'] is True


class TestUpdateNotes:

    @classmethod
    def _api_note_update(
            cls,
            app,
            client,
            note_id,
            subject,
            body,
            topics=(),
            expected_status_code=200,
    ):
        with mock_advising_note_s3_bucket(app):
            data = {
                'id': note_id,
                'subject': subject,
                'body': body,
                'topics': ','.join(topics),
            }
            response = client.post(
                '/api/notes/update',
                buffered=True,
                content_type='multipart/form-data',
                data=data,
            )
            assert response.status_code == expected_status_code
            return response.json

    def test_note_update_not_authenticated(self, app, mock_advising_note, client):
        """Returns 401 if not authenticated."""
        self._api_note_update(
            app,
            client,
            note_id=mock_advising_note.id,
            subject='Hack the subject!',
            body='Hack the body!',
            expected_status_code=401,
        )

    def test_unauthorized_update_note(self, app, client, fake_auth, mock_coe_advising_note):
        """Deny user's attempt to edit someone else's note."""
        original_subject = mock_coe_advising_note.subject
        fake_auth.login(asc_advisor_uid)
        assert self._api_note_update(
            app,
            client,
            note_id=mock_coe_advising_note.id,
            subject='Hack someone else\'s subject!',
            body='Hack someone else\'s body!',
            expected_status_code=403,
        )
        assert Note.find_by_id(note_id=mock_coe_advising_note.id).subject == original_subject

    def test_update_note_with_raw_url_in_body(self, app, client, fake_auth, mock_coe_advising_note):
        """Updates subject and body of note."""
        fake_auth.login(mock_coe_advising_note.author_uid)
        expected_subject = 'There must have been a plague of them'
        body = '<p>They were <a href="http://www.guzzle.com">www.guzzle.com</a> at <b>https://marsh.mallows.com</b> and <a href="http://www.foxnews.com">FOX news</a></p>'  # noqa: E501
        expected_body = '<p>They were <a href="http://www.guzzle.com">www.guzzle.com</a> at <b><a href="https://marsh.mallows.com" target="_blank">https://marsh.mallows.com</a></b> and <a href="http://www.foxnews.com">FOX news</a></p>'  # noqa: E501
        updated_note_response = self._api_note_update(
            app,
            client,
            note_id=mock_coe_advising_note.id,
            subject=expected_subject,
            body=body,
        )
        assert updated_note_response['read'] is True
        updated_note = Note.find_by_id(note_id=mock_coe_advising_note.id)
        assert updated_note.subject == expected_subject
        assert updated_note.body == expected_body

    def test_update_note_topics(self, app, client, fake_auth, mock_asc_advising_note):
        """Update note topics."""
        fake_auth.login(mock_asc_advising_note.author_uid)
        expected_topics = ['no color no contrast', 'joyful mask']
        api_json = self._api_note_update(
            app,
            client,
            note_id=mock_asc_advising_note.id,
            subject=mock_asc_advising_note.subject,
            body=mock_asc_advising_note.body,
            topics=expected_topics,
        )
        assert api_json['read'] is True
        assert len(api_json['topics']) == 2
        assert 'Joyful Mask' in api_json['topics']
        assert 'No Color No Contrast' in api_json['topics']

    def test_remove_note_topics(self, app, client, fake_auth, mock_asc_advising_note):
        """Delete note topics."""
        fake_auth.login(mock_asc_advising_note.author_uid)
        expected_topics = []
        api_json = self._api_note_update(
            app,
            client,
            note_id=mock_asc_advising_note.id,
            subject=mock_asc_advising_note.subject,
            body=mock_asc_advising_note.body,
            topics=expected_topics,
        )
        assert api_json['read'] is True
        assert not api_json['topics']


class TestDeleteNote:
    """Delete note API."""

    def test_not_authenticated(self, client):
        """You must log in to delete a note."""
        response = client.delete('/api/notes/delete/123')
        assert response.status_code == 401

    def test_unauthorized(self, client, fake_auth, mock_coe_advising_note):
        """Advisor cannot delete the note of another."""
        fake_auth.login('6446')
        response = client.delete(f'/api/notes/delete/{mock_coe_advising_note.id}')
        assert response.status_code == 403
        assert Note.find_by_id(mock_coe_advising_note.id)

    def test_advisor_cannot_delete(self, client, fake_auth, mock_coe_advising_note):
        """Advisor cannot delete her own note."""
        fake_auth.login(mock_coe_advising_note.author_uid)
        response = client.delete(f'/api/notes/delete/{mock_coe_advising_note.id}')
        assert response.status_code == 403
        assert Note.find_by_id(mock_coe_advising_note.id)

    def test_admin_delete(self, client, fake_auth, mock_coe_advising_note):
        """Admin can delete another user's note."""
        original_count_per_sid = len(Note.get_notes_by_sid(mock_coe_advising_note.sid))
        fake_auth.login(admin_uid)
        note_id = mock_coe_advising_note.id
        response = client.delete(f'/api/notes/delete/{note_id}')
        assert response.status_code == 200
        assert not Note.find_by_id(note_id)
        assert 1 == original_count_per_sid - len(Note.get_notes_by_sid(mock_coe_advising_note.sid))
        assert not Note.update(note_id=note_id, subject='Deleted note cannot be updated')

    def test_delete_note_with_topics(self, app, client, fake_auth):
        """Delete a note with topics."""
        fake_auth.login(coe_advisor_uid)
        note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject='Recontextualize open-source supply-chains',
            body='Conveniently repurpose enterprise-wide action items',
            topics=['strategic interfaces'],
        )
        # Log in as Admin and delete the note
        fake_auth.login(admin_uid)
        note_id = note.get('id')
        response = client.delete(f'/api/notes/delete/{note_id}')
        assert response.status_code == 200
        # TODO: add deleted_at column to NoteTopic and populate it when parent Note is deleted.
        # assert not NoteTopic.find_by_note_id(note_id)

    def test_delete_note_with_attachments(self, app, client, fake_auth):
        """Delete a note with two attachments."""
        fake_auth.login(coe_advisor_uid)
        base_dir = app.config['BASE_DIR']
        note = _api_note_create(
            app,
            client,
            author_id=AuthorizedUser.get_id_per_uid(coe_advisor_uid),
            sid=coe_student['sid'],
            subject='My little dog Lassie packed her bags and went out on to the porch',
            body='Then my little dog Lassie, she sailed off to the moon',
            attachments=[
                f'{base_dir}/fixtures/mock_advising_note_attachment_1.txt',
                f'{base_dir}/fixtures/mock_advising_note_attachment_2.txt',
            ],
        )
        attachment_ids = [a['id'] for a in note.get('attachments')]
        assert len(attachment_ids) == 2
        assert NoteAttachment.find_by_id(attachment_ids[0]) and NoteAttachment.find_by_id(attachment_ids[1])

        # Log in as Admin and delete the note
        fake_auth.login(admin_uid)
        note_id = note['id']
        response = client.delete(f'/api/notes/delete/{note_id}')
        assert response.status_code == 200
        assert not NoteAttachment.find_by_id(attachment_ids[0])
        assert not NoteAttachment.find_by_id(attachment_ids[1])


class TestStreamNoteAttachments:

    def test_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        assert client.get('/api/notes/attachment/9000000000_00002_1.pdf').status_code == 401

    def test_stream_attachment(self, app, client, fake_auth):
        with mock_legacy_note_attachment(app):
            fake_auth.login(coe_advisor_uid)
            response = client.get('/api/notes/attachment/9000000000_00002_1.pdf')
            assert response.status_code == 200
            assert response.headers['Content-Type'] == 'application/octet-stream'
            assert response.headers['Content-Disposition'] == "attachment; filename*=UTF-8''dog_eaten_homework.pdf"
            assert response.data == b'When in the course of human events, it becomes necessarf arf woof woof woof'

    def test_stream_attachment_reports_missing_files_not_found(self, app, client, fake_auth):
        with mock_legacy_note_attachment(app):
            fake_auth.login(asc_advisor_uid)
            response = client.get('/api/notes/attachment/h0ax.lol')
            assert response.status_code == 404
            assert response.data == b'Sorry, attachment not available.'


class TestAuthorSearch:

    def test_note_author_prefix_search_by_name(self, client, fake_auth):
        fake_auth.login(coe_advisor_uid)
        response = client.get('/api/notes/authors/find_by_name?q=Jo')
        assert response.status_code == 200
        assert len(response.json) == 2
        labels = [s['label'] for s in response.json]
        assert 'Robert Johnson' in labels
        assert 'Joni Mitchell' in labels


def _get_notes(client, uid):
    response = client.get(f'/api/student/by_uid/{uid}')
    assert response.status_code == 200
    return response.json['notifications']['note']


def _asc_note_with_attachment():
    for note in Note.get_notes_by_sid('11667051'):
        if len(note.attachments):
            return note
    return None


def _api_note_create(
        app,
        client,
        author_id,
        sid,
        subject,
        body,
        topics=(),
        attachments=(),
        template_attachment_ids=(),
        expected_status_code=200,
):
    with mock_advising_note_s3_bucket(app):
        data = {
            'authorId': author_id,
            'sid': sid,
            'subject': subject,
            'body': body,
            'topics': ','.join(topics),
            'templateAttachmentIds': ','.join(str(_id) for _id in template_attachment_ids),
        }
        for index, path in enumerate(attachments):
            data[f'attachment[{index}]'] = open(path, 'rb')
        response = client.post(
            '/api/notes/create',
            buffered=True,
            content_type='multipart/form-data',
            data=data,
        )
        assert response.status_code == expected_status_code
        return response.json


def _api_batch_note_create(
        app,
        client,
        author_id,
        subject,
        body,
        sids=None,
        cohort_ids=None,
        curated_group_ids=None,
        topics=(),
        attachments=(),
        template_attachment_ids=(),
        expected_status_code=200,
):
    with mock_advising_note_s3_bucket(app):
        data = {
            'authorId': author_id,
            'isBatchMode': sids and len(sids) > 1,
            'sids': sids or [],
            'cohortIds': cohort_ids or [],
            'curatedGroupIds': curated_group_ids or [],
            'subject': subject,
            'body': body,
            'templateAttachmentIds': template_attachment_ids,
            'topics': ','.join(topics),
        }
        for index, path in enumerate(attachments):
            data[f'attachment[{index}]'] = open(path, 'rb')
        response = client.post(
            '/api/notes/batch/create',
            buffered=True,
            content_type='multipart/form-data',
            data=data,
        )
        assert response.status_code == expected_status_code


def _api_batch_distinct_student_count(client, sids=(), cohort_ids=(), curated_group_ids=(), expected_status_code=200):
    response = client.post(
        '/api/notes/batch/distinct_student_count',
        data=json.dumps({
            'sids': sids,
            'cohortIds': cohort_ids,
            'curatedGroupIds': curated_group_ids,
        }),
        content_type='application/json',
    )
    assert response.status_code == expected_status_code
    return response.json['count'] if 'count' in response.json else None


def _get_curated_groups_ids_and_sids(advisor):
    sids = []
    curated_group_ids = []
    for curated_group in CuratedGroup.get_curated_groups_by_owner_id(advisor.id):
        curated_group_ids.append(curated_group.id)
        sids = sids + CuratedGroup.get_all_sids(curated_group.id)
    return curated_group_ids, sids


def _get_cohorts_ids_and_sids(advisor):
    cohort_ids = [c['id'] for c in all_cohorts_owned_by(advisor.uid)]
    sids = []
    for cohort_id in cohort_ids:
        sids = sids + CohortFilter.get_sids(cohort_id)
    return cohort_ids, sids
