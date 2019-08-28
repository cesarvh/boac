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

import urllib.parse

from boac.api.errors import BadRequestError, ForbiddenRequestError, ResourceNotFoundError
from boac.api.util import get_note_attachments_from_http_post, get_note_topics_from_http_post, get_template_attachment_ids_from_http_post
from boac.externals import data_loch
from boac.lib.http import tolerant_jsonify
from boac.lib.util import get as get_param, is_int, process_input_from_rich_text_editor, to_bool_or_none
from boac.merged.advising_note import get_batch_distinct_sids, get_boa_attachment_stream, get_legacy_attachment_stream, note_to_compatible_json
from boac.merged.calnet import get_calnet_user_for_uid
from boac.models.cohort_filter import CohortFilter
from boac.models.curated_group import CuratedGroup
from boac.models.note import Note
from boac.models.note_read import NoteRead
from boac.models.topic import Topic
from flask import current_app as app, request, Response
from flask_login import current_user, login_required


@app.route('/api/note/<note_id>')
@login_required
def get_note(note_id):
    note = Note.find_by_id(note_id=note_id)
    if not note:
        raise ResourceNotFoundError('Note not found')
    note_read = NoteRead.when_user_read_note(current_user.get_id(), str(note.id))
    return tolerant_jsonify(_boa_note_to_compatible_json(note=note, note_read=note_read))


@app.route('/api/notes/<note_id>/mark_read', methods=['POST'])
@login_required
def mark_read(note_id):
    if NoteRead.find_or_create(current_user.get_id(), note_id):
        return tolerant_jsonify({'status': 'created'}, status=201)
    else:
        raise BadRequestError(f'Failed to mark note {note_id} as read by user {current_user.get_uid()}')


@app.route('/api/notes/create', methods=['POST'])
@login_required
def create_note():
    params = request.form
    sid = params.get('sid', None)
    subject = params.get('subject', None)
    body = params.get('body', None)
    topics = get_note_topics_from_http_post()
    if not sid or not subject:
        raise BadRequestError('Note creation requires \'subject\' and \'sid\'')
    if current_user.is_admin or not len(current_user.dept_codes):
        raise ForbiddenRequestError('Sorry, Admin users cannot create advising notes')

    author_profile = _get_author_profile()
    attachments = get_note_attachments_from_http_post(tolerate_none=True)

    note = Note.create(
        **author_profile,
        subject=subject,
        body=process_input_from_rich_text_editor(body),
        topics=topics,
        sid=sid,
        attachments=attachments,
        template_attachment_ids=get_template_attachment_ids_from_http_post(),
    )
    note_read = NoteRead.find_or_create(current_user.get_id(), note.id)
    return tolerant_jsonify(_boa_note_to_compatible_json(note=note, note_read=note_read))


@app.route('/api/notes/batch/create', methods=['POST'])
@login_required
def batch_create_notes():
    params = request.form
    sids = _get_sids_for_note_creation()
    subject = params.get('subject', None)
    body = params.get('body', None)
    topics = get_note_topics_from_http_post()
    if not sids or not subject:
        raise BadRequestError('Note creation requires \'subject\' and \'sid\'')
    if current_user.is_admin or not len(current_user.dept_codes):
        raise ForbiddenRequestError('Sorry, Admin users cannot create advising notes')

    author_profile = _get_author_profile()
    attachments = get_note_attachments_from_http_post(tolerate_none=True)

    note_ids_per_sid = Note.create_batch(
        author_id=current_user.to_api_json()['id'],
        **author_profile,
        subject=subject,
        body=process_input_from_rich_text_editor(body),
        topics=topics,
        sids=sids,
        attachments=attachments,
        template_attachment_ids=get_template_attachment_ids_from_http_post(),
    )
    return tolerant_jsonify(note_ids_per_sid)


@app.route('/api/notes/batch/distinct_student_count', methods=['POST'])
@login_required
def distinct_student_count():
    params = request.get_json()
    sids = get_param(params, 'sids', None)
    cohort_ids = get_param(params, 'cohortIds', None)
    curated_group_ids = get_param(params, 'curatedGroupIds', None)
    if cohort_ids or curated_group_ids:
        count = len(get_batch_distinct_sids(sids, cohort_ids, curated_group_ids))
    else:
        count = len(sids)
    return tolerant_jsonify({
        'count': count,
    })


@app.route('/api/notes/update', methods=['POST'])
@login_required
def update_note():
    params = request.form
    note_id = params.get('id', None)
    subject = params.get('subject', None)
    body = params.get('body', None)
    topics = get_note_topics_from_http_post()
    if not note_id or not subject:
        raise BadRequestError('Note requires \'id\' and \'subject\'')
    if Note.find_by_id(note_id=note_id).author_uid != current_user.get_uid():
        raise ForbiddenRequestError('Sorry, you are not the author of this note.')
    note = Note.update(
        note_id=note_id,
        subject=subject,
        body=process_input_from_rich_text_editor(body),
        topics=topics,
    )
    note_read = NoteRead.find_or_create(current_user.get_id(), note_id)
    return tolerant_jsonify(_boa_note_to_compatible_json(note=note, note_read=note_read))


@app.route('/api/notes/delete/<note_id>', methods=['DELETE'])
@login_required
def delete_note(note_id):
    if not current_user.is_admin:
        raise ForbiddenRequestError('Sorry, you are not authorized to delete notes.')
    note = Note.find_by_id(note_id=note_id)
    if not note:
        raise ResourceNotFoundError('Note not found')
    Note.delete(note_id=note_id)
    return tolerant_jsonify({'message': f'Note {note_id} deleted'}), 200


@app.route('/api/notes/authors/find_by_name', methods=['GET'])
@login_required
def find_note_authors_by_name():
    query = request.args.get('q')
    if not query:
        raise BadRequestError('Search query must be supplied')
    limit = request.args.get('limit')
    query_fragments = filter(None, query.upper().split(' '))
    authors = data_loch.match_advising_note_authors_by_name(query_fragments, limit=limit)

    def _author_feed(a):
        return {
            'label': ' '.join([a.get('first_name', ''), a.get('last_name', '')]),
            'sid': a.get('sid'),
            'uid': a.get('uid'),
        }
    return tolerant_jsonify([_author_feed(a) for a in authors])


@app.route('/api/notes/topics', methods=['GET'])
@login_required
def get_topics():
    include_deleted = to_bool_or_none(request.args.get('includeDeleted'))
    topics = Topic.get_all(include_deleted=include_deleted)
    return tolerant_jsonify([topic.to_api_json() for topic in topics])


@app.route('/api/notes/<note_id>/attachment', methods=['POST'])
@login_required
def add_attachment(note_id):
    if Note.find_by_id(note_id=note_id).author_uid != current_user.get_uid():
        raise ForbiddenRequestError('Sorry, you are not the author of this note.')
    attachments = get_note_attachments_from_http_post()
    if len(attachments) != 1:
        raise BadRequestError('A single attachment file must be supplied.')
    note = Note.add_attachment(
        note_id=note_id,
        attachment=attachments[0],
    )
    note_json = note.to_api_json()
    return tolerant_jsonify(
        note_to_compatible_json(
            note=note_json,
            note_read=NoteRead.find_or_create(current_user.get_id(), note_id),
            attachments=note_json.get('attachments'),
            topics=note_json.get('topics'),
        ),
    )


@app.route('/api/notes/<note_id>/attachment/<attachment_id>', methods=['DELETE'])
@login_required
def remove_attachment(note_id, attachment_id):
    existing_note = Note.find_by_id(note_id=note_id)
    if not existing_note:
        raise BadRequestError('Note id not found.')
    if existing_note.author_uid != current_user.get_uid() and not current_user.is_admin:
        raise ForbiddenRequestError('You are not authorized to remove attachments from this note.')
    note = Note.delete_attachment(
        note_id=note_id,
        attachment_id=int(attachment_id),
    )
    note_json = note.to_api_json()
    return tolerant_jsonify(
        note_to_compatible_json(
            note=note_json,
            note_read=NoteRead.find_or_create(current_user.get_id(), note_id),
            attachments=note_json.get('attachments'),
            topics=note_json.get('topics'),
        ),
    )


@app.route('/api/notes/attachment/<attachment_id>', methods=['GET'])
@login_required
def download_attachment(attachment_id):
    is_legacy = not is_int(attachment_id)
    id_ = attachment_id if is_legacy else int(attachment_id)
    stream_data = get_legacy_attachment_stream(id_) if is_legacy else get_boa_attachment_stream(id_)
    if not stream_data or not stream_data['stream']:
        return Response('Sorry, attachment not available.', mimetype='text/html', status=404)
    r = Response(stream_data['stream'])
    r.headers['Content-Type'] = 'application/octet-stream'
    encoding_safe_filename = urllib.parse.quote(stream_data['filename'].encode('utf8'))
    r.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{encoding_safe_filename}"
    return r


def _get_sids_for_note_creation():
    def _get_param_as_set(key):
        values = set()
        for entry in request.form.getlist(key):
            # The use of 'form.getlist' might give us a list with one entry: comma-separated values
            split = str(entry).split(',')
            for value in list(filter(None, split)):
                values.add(value)
        return values

    cohort_ids = set(_get_param_as_set('cohortIds'))
    curated_group_ids = set(_get_param_as_set('curatedGroupIds'))
    sids = _get_param_as_set('sids')
    sids = sids.union(_get_sids_per_cohorts(cohort_ids))
    return list(sids.union(_get_sids_per_curated_groups(curated_group_ids)))


def _get_sids_per_cohorts(cohort_ids=None):
    sids = set()
    for cohort_id in cohort_ids or ():
        if cohort_id:
            sids = sids.union(CohortFilter.get_sids(cohort_id))
    return sids


def _get_sids_per_curated_groups(curated_group_ids=None):
    sids = set()
    for curated_group_id in curated_group_ids or ():
        if curated_group_id:
            sids = sids.union(CuratedGroup.get_all_sids(curated_group_id))
    return sids


def _get_author_profile():
    author = current_user.to_api_json()
    calnet_profile = get_calnet_user_for_uid(app, author['uid'])
    if calnet_profile and calnet_profile.get('departments'):
        dept_codes = [dept.get('code') for dept in calnet_profile.get('departments')]
    else:
        dept_codes = current_user.dept_codes
    if calnet_profile and calnet_profile.get('title'):
        role = calnet_profile['title']
    elif current_user.departments:
        role = current_user.departments[0]['role']
    else:
        role = None

    return {
        'author_uid': author['uid'],
        'author_name': author['name'],
        'author_role': role,
        'author_dept_codes': dept_codes,
    }


def _boa_note_to_compatible_json(note, note_read):
    note_json = note.to_api_json()
    return {
        **note_to_compatible_json(
            note=note_json,
            note_read=note_read,
            attachments=note_json.get('attachments'),
            topics=note_json.get('topics'),
        ),
        **{
            'message': note.body,
            'type': 'note',
        },
    }
