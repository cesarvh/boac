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

from boac import db


class NoteTopic(db.Model):
    __tablename__ = 'note_topics'

    id = db.Column(db.Integer, nullable=False, primary_key=True)  # noqa: A003
    note_id = db.Column(db.Integer, db.ForeignKey('notes.id'), nullable=False, onupdate='cascade')
    topic = db.Column(db.String(255), nullable=False)
    author_uid = db.Column(db.String(255), db.ForeignKey('authorized_users.uid'), nullable=False)
    note = db.relationship('Note', back_populates='topics')

    def __init__(self, note_id, topic, author_uid):
        self.note_id = note_id
        self.topic = topic
        self.author_uid = author_uid

    @classmethod
    def create_note_topic(cls, note, topic, author_uid):
        return NoteTopic(
            note_id=note.id,
            topic=topic,
            author_uid=author_uid,
        )

    @classmethod
    def find_by_note_id(cls, note_id):
        return cls.query.filter(cls.note_id == note_id).all()

    def to_api_json(self):
        return self.topic
