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

coe_advisor = '1133399'


class TestUpdateNotes:

    @classmethod
    def _get_notes(cls, client, uid):
        response = client.get(f'/api/student/{uid}')
        assert response.status_code == 200
        return response.json['notifications']['note']

    def test_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        assert client.post('/api/notes/11667051-00001/mark_read').status_code == 401

    def test_mark_note_read(self, fake_auth, client):
        """Marks a note as read."""
        fake_auth.login(coe_advisor)

        all_notes_unread = self._get_notes(client, 61889)
        assert len(all_notes_unread) == 4
        for note in all_notes_unread:
            assert note['read'] is False

        response = client.post('/api/notes/11667051-00001/mark_read')
        assert response.status_code == 201

        non_legacy_note_id = all_notes_unread[3]['id']
        response = client.post(f'/api/notes/{non_legacy_note_id}/mark_read')
        assert response.status_code == 201

        all_notes_one_read = self._get_notes(client, 61889)
        assert len(all_notes_one_read) == 4
        assert all_notes_one_read[0]['id'] == '11667051-00001'
        assert all_notes_one_read[0]['read'] is True
        assert all_notes_one_read[1]['id'] == '11667051-00002'
        assert all_notes_one_read[1]['read'] is False
        assert all_notes_one_read[3]['id'] == non_legacy_note_id
        assert all_notes_one_read[3]['read'] is True