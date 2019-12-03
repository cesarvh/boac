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

from boac import std_commit
from boac.models.appointment import Appointment
from boac.models.appointment_read import AppointmentRead
from boac.models.authorized_user import AuthorizedUser
from boac.models.drop_in_advisor import DropInAdvisor
import simplejson as json
from sqlalchemy import and_
from tests.util import override_config

coe_advisor_uid = '90412'
coe_drop_in_advisor_uid = '90412'
coe_scheduler_uid = '6972201'
l_s_college_advisor_uid = '188242'
l_s_college_drop_in_advisor_uid = '53791'
l_s_college_scheduler_uid = '19735'


class AppointmentTestUtil:

    @classmethod
    def cancel_appointment(
            cls,
            client,
            appointment_id,
            cancel_reason,
            cancel_reason_explained=None,
            expected_status_code=200,
    ):
        data = {
            'cancelReason': cancel_reason,
            'cancelReasonExplained': cancel_reason_explained,
        }
        response = client.post(
            f'/api/appointments/{appointment_id}/cancel',
            data=json.dumps(data),
            content_type='application/json',
        )
        assert response.status_code == expected_status_code
        return response.json

    @classmethod
    def check_in_appointment(cls, client, appointment_id, advisor_uid=None, expected_status_code=200):
        data = {
            'advisorUid': advisor_uid,
        }
        response = client.post(
            f'/api/appointments/{appointment_id}/check_in',
            data=json.dumps(data),
            content_type='application/json',
        )
        assert response.status_code == expected_status_code
        return response.json

    @classmethod
    def create_appointment(
            cls,
            client,
            dept_code,
            details=None,
            advisor_dept_codes=None,
            advisor_name=None,
            advisor_role=None,
            advisor_uid=None,
            expected_status_code=200,
    ):
        data = {
            'advisorDeptCodes': advisor_dept_codes,
            'advisorName': advisor_name,
            'advisorRole': advisor_role,
            'advisorUid': advisor_uid,
            'appointmentType': 'Drop-in',
            'deptCode': dept_code,
            'details': details or '',
            'sid': '3456789012',
            'topics': ['Topic for appointments, 1', 'Topic for appointments, 4'],
        }
        response = client.post(
            '/api/appointments/create',
            data=json.dumps(data),
            content_type='application/json',
        )
        assert response.status_code == expected_status_code
        return response.json


class TestCreateAppointment:

    @classmethod
    def _get_waitlist(cls, client, dept_code, expected_status_code=200):
        response = client.get(f'/api/appointments/waitlist/{dept_code}')
        assert response.status_code == expected_status_code
        if response.status_code == 200:
            return response.json['waitlist']

    def test_create_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        AppointmentTestUtil.create_appointment(client, 'COENG', expected_status_code=401)

    def test_create_appointment_as_coe_scheduler(self, client, fake_auth):
        """Scheduler can create appointments."""
        fake_auth.login(coe_scheduler_uid)
        details = 'Aloysius has some questions.'
        appointment = AppointmentTestUtil.create_appointment(client, 'COENG', details)
        appointment_id = appointment['id']
        waitlist = self._get_waitlist(client, 'COENG')
        matching = next((a for a in waitlist['unresolved'] if a['details'] == details), None)
        assert matching
        assert appointment_id == matching['id']
        assert appointment['read'] is True
        assert appointment['status'] == 'waiting'
        assert appointment['student']['sid'] == '3456789012'
        assert appointment['student']['name'] == 'Paul Kerschen'
        assert appointment['student']['photoUrl']
        assert appointment['appointmentType'] == 'Drop-in'
        assert len(appointment['topics']) == 2
        # Verify that a deleted appointment is off the waitlist
        Appointment.delete(appointment_id)
        waitlist = self._get_waitlist(client, 'COENG')
        assert next((a for a in waitlist['unresolved'] if a['details'] == details), None) is None

    def test_create_pre_reserved_appointment_for_specific_advisor(self, client, fake_auth):
        fake_auth.login(coe_scheduler_uid)
        details = 'Aloysius has some questions.'
        advisor_dept_codes = ['COENG']
        advisor_name = 'Alfred E. Neuman'
        advisor_role = 'College Advisor'
        appointment = AppointmentTestUtil.create_appointment(
            client=client,
            dept_code='COENG',
            details=details,
            advisor_dept_codes=advisor_dept_codes,
            advisor_name=advisor_name,
            advisor_role=advisor_role,
            advisor_uid=coe_drop_in_advisor_uid,
        )
        appointment_id = appointment['id']
        waitlist = self._get_waitlist(client, 'COENG')
        matching = next((a for a in waitlist['unresolved'] if a['details'] == details), None)
        assert appointment_id == matching['id']
        assert appointment['advisorDepartments'][0]['code'] == 'COENG'
        assert appointment['advisorName'] == advisor_name
        assert appointment['advisorRole'] == advisor_role
        assert appointment['advisorUid'] == coe_drop_in_advisor_uid
        assert appointment['read'] is True
        assert appointment['status'] == 'reserved'
        assert appointment['statusBy']['uid'] == coe_drop_in_advisor_uid

    def test_other_departments_forbidden(self, client, fake_auth):
        fake_auth.login(coe_scheduler_uid)
        AppointmentTestUtil.create_appointment(client, 'UWASC', expected_status_code=403)

    def test_nonsense_department_not_found(self, client, fake_auth):
        fake_auth.login(coe_scheduler_uid)
        AppointmentTestUtil.create_appointment(client, 'DINGO', expected_status_code=404)

    def test_feature_flag(self, client, fake_auth, app):
        """Returns 404 if the Appointments feature is false."""
        with override_config(app, 'FEATURE_FLAG_ADVISOR_APPOINTMENTS', False):
            fake_auth.login(coe_advisor_uid)
            self._get_waitlist(client, 'COENG', expected_status_code=401)


class TestGetAppointment:

    @classmethod
    def _get_appointment(cls, client, appointment_id, expected_status_code=200):
        response = client.get(f'/api/appointments/{appointment_id}')
        assert response.status_code == expected_status_code
        return response.json

    def test_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        self._get_appointment(client, 'COENG', expected_status_code=401)

    def test_not_authorized(self, client, fake_auth):
        """Returns 401 if user is scheduler."""
        fake_auth.login(coe_scheduler_uid)
        self._get_appointment(client, 1, 401)

    def test_get_appointment(self, client, fake_auth):
        """Get appointment."""
        fake_auth.login(coe_advisor_uid)
        appointment = self._get_appointment(client, 1)
        assert appointment
        assert appointment['id'] == 1
        assert appointment['status'] is not None

    def test_feature_flag(self, client, fake_auth, app):
        """Returns 404 if the Appointments feature is false."""
        with override_config(app, 'FEATURE_FLAG_ADVISOR_APPOINTMENTS', False):
            fake_auth.login(coe_advisor_uid)
            self._get_appointment(client, 'COENG', expected_status_code=401)


class TestAppointmentUpdate:

    @classmethod
    def _api_appointment_update(
            cls,
            client,
            appointment_id,
            details,
            topics=(),
            expected_status_code=200,
    ):
        data = {
            'id': appointment_id,
            'details': details,
            'topics': topics,
        }
        response = client.post(
            f'/api/appointments/{appointment_id}/update',
            data=json.dumps(data),
            content_type='application/json',
        )
        assert response.status_code == expected_status_code
        return response.json

    def test_not_authenticated(self, app, client):
        """Returns 401 if not authenticated."""
        self._api_appointment_update(client, 1, 'Hack the appointment!', expected_status_code=401)

    def test_deny_advisor(self, app, client, fake_auth):
        """Returns 401 if user is a non-dropin advisor."""
        fake_auth.login(l_s_college_advisor_uid)
        self._api_appointment_update(client, 1, 'Advise the appointment!', expected_status_code=401)

    def test_appointment_not_found(self, app, client, fake_auth):
        """Returns 404 if appointment is not found."""
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        self._api_appointment_update(client, 99999999, 'Drop in the appointment!', expected_status_code=404)

    def test_update_appointment_details(self, app, client, fake_auth):
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        created = AppointmentTestUtil.create_appointment(client, 'QCADV')
        expected_details = 'Why lookst thou so? - With my crossbow I shot the albatross.'
        self._api_appointment_update(
            client,
            created['id'],
            expected_details,
            created['topics'],
        )
        updated_appt = Appointment.find_by_id(appointment_id=created['id'])
        assert updated_appt.details == expected_details

    def test_update_appointment_topics(self, app, client, fake_auth):
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        created = AppointmentTestUtil.create_appointment(client, 'QCADV')
        expected_topics = ['Practice Makes Perfect', 'French Film Blurred']
        details = created['details']
        appt_id = created['id']
        updated = self._api_appointment_update(client, appt_id, details, expected_topics)
        assert len(updated['topics']) == 2
        assert set(updated['topics']) == set(expected_topics)

        # Remove topics
        removed = self._api_appointment_update(client, appt_id, details, ['Practice Makes Perfect'])
        std_commit(allow_test_environment=True)
        assert len(removed['topics']) == 1

        # Finally, re-add topics
        restored = self._api_appointment_update(client, appt_id, details, expected_topics)
        std_commit(allow_test_environment=True)
        assert set(restored['topics']) == set(expected_topics)


class TestAppointmentCancel:

    def test_mark_read_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        AppointmentTestUtil.cancel_appointment(client, 1, 'Cancelled by student', expected_status_code=401)

    def test_deny_advisor(self, app, client, fake_auth):
        """Returns 403 if user is an advisor without drop_in responsibilities."""
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        AppointmentTestUtil.cancel_appointment(client, 1, 'Cancelled by advisor', expected_status_code=403)

    def test_double_cancel_conflict(self, app, client, fake_auth):
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        waiting = AppointmentTestUtil.create_appointment(client, 'QCADV')
        AppointmentTestUtil.cancel_appointment(client, waiting['id'], 'Cancelled by weasels')
        fake_auth.login(l_s_college_scheduler_uid)
        AppointmentTestUtil.cancel_appointment(client, waiting['id'], 'Cancelled by stoats', expected_status_code=400)

    def test_check_in_cancel_conflict(self, app, client, fake_auth):
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        waiting = AppointmentTestUtil.create_appointment(client, 'QCADV')
        AppointmentTestUtil.check_in_appointment(client, waiting['id'], l_s_college_drop_in_advisor_uid)
        fake_auth.login(l_s_college_scheduler_uid)
        AppointmentTestUtil.cancel_appointment(client, waiting['id'], 'Cancelled by wolves', expected_status_code=400)

    def test_appointment_cancel(self, app, client, fake_auth):
        """Drop-in advisor can cancel appointment."""
        dept_code = 'QCADV'
        advisor = DropInAdvisor.advisors_for_dept_code(dept_code)[0]
        user = AuthorizedUser.find_by_id(advisor.authorized_user_id)
        fake_auth.login(user.uid)
        waiting = AppointmentTestUtil.create_appointment(client, dept_code)
        appointment = AppointmentTestUtil.cancel_appointment(client, waiting['id'], 'Cancelled by wolves')
        appointment_id = appointment['id']
        assert appointment_id == waiting['id']
        assert appointment['status'] == 'cancelled'
        assert appointment['statusBy']['id'] == user.id
        assert appointment['statusBy']['uid'] == user.uid
        assert appointment['statusDate'] is not None
        Appointment.delete(appointment_id)

    def test_feature_flag(self, client, fake_auth, app):
        """Appointments feature is false."""
        dept_code = 'QCADV'
        advisor = DropInAdvisor.advisors_for_dept_code(dept_code)[0]
        fake_auth.login(AuthorizedUser.find_by_id(advisor.authorized_user_id).uid)
        appointment = AppointmentTestUtil.create_appointment(client, dept_code)
        with override_config(app, 'FEATURE_FLAG_ADVISOR_APPOINTMENTS', False):
            AppointmentTestUtil.cancel_appointment(
                client,
                appointment_id=appointment['id'],
                cancel_reason='Cancelled by the power of the mind',
                expected_status_code=401,
            )


class TestAppointmentCheckIn:

    def test_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        AppointmentTestUtil.check_in_appointment(client, 1, l_s_college_advisor_uid, expected_status_code=401)

    def test_deny_advisor(self, app, client, fake_auth):
        """Returns 401 if user is not a drop-in advisor."""
        fake_auth.login(l_s_college_advisor_uid)
        AppointmentTestUtil.check_in_appointment(client, 1, l_s_college_advisor_uid, expected_status_code=401)

    def test_double_check_in_conflict(self, app, client, fake_auth):
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        waiting = AppointmentTestUtil.create_appointment(client, 'QCADV')
        AppointmentTestUtil.check_in_appointment(client, waiting['id'], l_s_college_drop_in_advisor_uid)
        fake_auth.login(l_s_college_scheduler_uid)
        AppointmentTestUtil.cancel_appointment(client, waiting['id'], 'Cancelled by wolves', expected_status_code=400)

    def test_cancel_check_in_conflict(self, app, client, fake_auth):
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        waiting = AppointmentTestUtil.create_appointment(client, 'QCADV')
        AppointmentTestUtil.cancel_appointment(client, waiting['id'], 'Cancelled by wolves')
        fake_auth.login(l_s_college_scheduler_uid)
        AppointmentTestUtil.check_in_appointment(client, waiting['id'], l_s_college_drop_in_advisor_uid, expected_status_code=400)

    def test_feature_flag(self, client, fake_auth, app):
        """Appointments feature is false."""
        dept_code = 'QCADV'
        advisor = DropInAdvisor.advisors_for_dept_code(dept_code)[0]
        fake_auth.login(AuthorizedUser.find_by_id(advisor.authorized_user_id).uid)
        appointment = AppointmentTestUtil.create_appointment(client, dept_code)
        with override_config(app, 'FEATURE_FLAG_ADVISOR_APPOINTMENTS', False):
            AppointmentTestUtil.check_in_appointment(client, appointment['id'], l_s_college_drop_in_advisor_uid, expected_status_code=401)


class TestAppointmentReserve:

    @classmethod
    def _reserve_appointment(cls, client, appointment_id, advisor_uid, expected_status_code=200):
        data = {
            'advisorUid': advisor_uid,
        }
        response = client.post(
            f'/api/appointments/{appointment_id}/reserve',
            data=json.dumps(data),
            content_type='application/json',
        )
        assert response.status_code == expected_status_code
        return response.json

    @classmethod
    def _unreserve_appointment(cls, client, appointment_id, expected_status_code=200):
        response = client.post(f'/api/appointments/{appointment_id}/unreserve')
        assert response.status_code == expected_status_code
        return response.json

    def test_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        self._reserve_appointment(client, 1, l_s_college_advisor_uid, expected_status_code=401)
        self._unreserve_appointment(client, 1, expected_status_code=401)

    def test_deny_advisor(self, app, client, fake_auth):
        """Returns 401 if user is not a drop-in advisor."""
        fake_auth.login(l_s_college_advisor_uid)
        self._reserve_appointment(client, 1, l_s_college_advisor_uid, expected_status_code=401)
        self._unreserve_appointment(client, 1, expected_status_code=401)

    def test_cancel_reserve_conflict(self, app, client, fake_auth):
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        waiting = AppointmentTestUtil.create_appointment(client, 'QCADV')
        AppointmentTestUtil.cancel_appointment(client, waiting['id'], 'Cancelled by wolves')
        fake_auth.login(l_s_college_scheduler_uid)
        self._reserve_appointment(client, waiting['id'], l_s_college_drop_in_advisor_uid, expected_status_code=400)

    def test_check_in_reserve_conflict(self, app, client, fake_auth):
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        waiting = AppointmentTestUtil.create_appointment(client, 'QCADV')
        AppointmentTestUtil.check_in_appointment(client, waiting['id'], l_s_college_drop_in_advisor_uid)
        fake_auth.login(l_s_college_scheduler_uid)
        self._reserve_appointment(client, waiting['id'], l_s_college_drop_in_advisor_uid, expected_status_code=400)

    def test_unreserve_appointment_reserved_by_other(self, app, client, fake_auth):
        """Returns 401 if user un-reserves an appointment which is reserved by another."""
        waiting = Appointment.query.filter(
            and_(Appointment.status == 'waiting', Appointment.deleted_at == None),
        ).first()  # noqa: E711
        advisor = AuthorizedUser.find_by_id(waiting.created_by)
        fake_auth.login(advisor.uid)
        self._reserve_appointment(client, waiting.id, advisor.uid)
        fake_auth.login(l_s_college_advisor_uid)
        self._unreserve_appointment(client, 1, expected_status_code=401)

    def test_reserve_appointment(self, app, client, fake_auth):
        """Drop-in advisor can reserve an appointment."""
        dept_code = 'QCADV'
        advisor = DropInAdvisor.advisors_for_dept_code(dept_code)[0]
        user = AuthorizedUser.find_by_id(advisor.authorized_user_id)
        fake_auth.login(user.uid)
        waiting = AppointmentTestUtil.create_appointment(client, dept_code)
        appointment = self._reserve_appointment(client, waiting['id'], user.uid)
        assert appointment['status'] == 'reserved'
        assert appointment['statusDate'] is not None
        assert appointment['statusBy']['id'] == user.id
        Appointment.delete(appointment['id'])

    def test_steal_appointment_reservation(self, app, client, fake_auth):
        """Reserve an appointment that another advisor has reserved."""
        dept_code = 'COENG'
        advisor_1 = DropInAdvisor.advisors_for_dept_code(dept_code)[0]
        user_1 = AuthorizedUser.find_by_id(advisor_1.authorized_user_id)
        fake_auth.login(user_1.uid)
        waiting = AppointmentTestUtil.create_appointment(client, dept_code)
        appointment = self._reserve_appointment(client, waiting['id'], user_1.uid)
        assert appointment['status'] == 'reserved'
        assert appointment['statusDate'] is not None
        assert appointment['statusBy']['id'] == user_1.id
        client.get('/api/auth/logout')

        # Another advisor comes along...
        advisor_2 = DropInAdvisor.advisors_for_dept_code(dept_code)[1]
        user_2 = AuthorizedUser.find_by_id(advisor_2.authorized_user_id)
        fake_auth.login(user_2.uid)
        appointment = self._reserve_appointment(client, waiting['id'], user_2.uid)
        assert appointment['status'] == 'reserved'
        assert appointment['statusDate'] is not None
        assert appointment['statusBy']['id'] == user_2.id
        # Clean up
        Appointment.delete(appointment['id'])

    def test_unreserve_appointment(self, app, client, fake_auth):
        """Drop-in advisor can un-reserve an appointment."""
        dept_code = 'QCADV'
        advisor = DropInAdvisor.advisors_for_dept_code(dept_code)[0]
        user = AuthorizedUser.find_by_id(advisor.authorized_user_id)
        fake_auth.login(user.uid)
        waiting = AppointmentTestUtil.create_appointment(client, dept_code)
        reserved = self._reserve_appointment(client, waiting['id'], user.uid)
        assert reserved['status'] == 'reserved'
        assert reserved['statusDate']
        assert reserved['statusBy']['id'] == user.id
        assert reserved['statusBy']['uid'] == user.uid
        assert 'name' in reserved['statusBy']
        appointment = self._unreserve_appointment(client, waiting['id'])
        assert appointment['status'] == 'waiting'
        assert appointment['statusDate'] is not None
        assert appointment['statusBy']['id'] == user.id
        Appointment.delete(appointment['id'])

    def test_feature_flag(self, client, fake_auth, app):
        """Appointments feature is false."""
        dept_code = 'QCADV'
        advisor = DropInAdvisor.advisors_for_dept_code(dept_code)[0]
        advisor_uid = AuthorizedUser.find_by_id(advisor.authorized_user_id).uid
        fake_auth.login(advisor_uid)
        appointment = AppointmentTestUtil.create_appointment(client, dept_code)
        with override_config(app, 'FEATURE_FLAG_ADVISOR_APPOINTMENTS', False):
            self._reserve_appointment(client, appointment['id'], advisor_uid, expected_status_code=401)


class TestAppointmentReopen:

    @classmethod
    def _reopen_appointment(cls, client, appointment_id, expected_status_code=200):
        response = client.get(f'/api/appointments/{appointment_id}/reopen')
        assert response.status_code == expected_status_code
        return response.json

    def test_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        self._reopen_appointment(client, 1, expected_status_code=401)

    def test_deny_advisor(self, app, client, fake_auth):
        """Returns 401 if user is a non-dropin advisor."""
        fake_auth.login(l_s_college_advisor_uid)
        self._reopen_appointment(client, 1, expected_status_code=401)

    def test_appointment_not_found(self, app, client, fake_auth):
        """Returns 404 if appointment is not found."""
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        self._reopen_appointment(client, 9999999, expected_status_code=404)

    def test_reopen_appointment(self, app, client, fake_auth):
        """Drop-in advisor can reopen an appointment."""
        dept_code = 'QCADV'
        advisor = DropInAdvisor.advisors_for_dept_code(dept_code)[0]
        user = AuthorizedUser.find_by_id(advisor.authorized_user_id)
        fake_auth.login(user.uid)
        appointment = AppointmentTestUtil.create_appointment(client, dept_code)
        cancelled = AppointmentTestUtil.cancel_appointment(client, appointment['id'], 'Accidental cancel, whoopsie')
        assert cancelled['status'] == 'cancelled'
        appointment = self._reopen_appointment(client, cancelled['id'])
        assert appointment['status'] == 'waiting'
        assert appointment['statusDate'] is not None
        assert appointment['statusBy']['id'] == user.id
        Appointment.delete(appointment['id'])


class TestAppointmentWaitlist:

    @classmethod
    def _get_waitlist(cls, client, dept_code, expected_status_code=200):
        response = client.get(f'/api/appointments/waitlist/{dept_code}')
        assert response.status_code == expected_status_code
        if response.status_code == 200:
            return response.json['waitlist']

    def test_mark_read_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        self._get_waitlist(client, 'COENG', expected_status_code=401)

    def test_unrecognized_dept_code(self, app, client, fake_auth):
        """Returns 404 if requested dept_code is invalid."""
        fake_auth.login(l_s_college_scheduler_uid)
        self._get_waitlist(client, 'BOGUS', expected_status_code=404)

    def test_deny_advisor(self, app, client, fake_auth):
        """Returns 401 if user is not a drop-in advisor."""
        fake_auth.login(l_s_college_advisor_uid)
        self._get_waitlist(client, 'QCADV', expected_status_code=401)

    def test_l_and_s_advisor_cannot_view_coe_waitlist(self, app, client, fake_auth):
        """L&S advisor cannot view COE appointments (waitlist)."""
        fake_auth.login(l_s_college_scheduler_uid)
        self._get_waitlist(client, 'COENG', expected_status_code=403)

    def test_coe_scheduler_waitlist(self, app, client, fake_auth):
        """Waitlist is properly sorted for COE drop-in advisor."""
        fake_auth.login(coe_drop_in_advisor_uid)
        waitlist = self._get_waitlist(client, 'COENG')
        assert len(waitlist['unresolved']) == 3
        assert len(waitlist['resolved']) > 2
        for appt in waitlist['unresolved']:
            assert appt['status'] in ('reserved', 'waiting')
        for appt in waitlist['resolved']:
            assert appt['status'] in ('checked_in', 'cancelled')

    def test_waitlist_include_checked_in_and_cancelled(self, app, client, fake_auth):
        """For scheduler, the waitlist has appointments with event type 'waiting' or 'reserved'."""
        fake_auth.login(coe_scheduler_uid)
        appointments = self._get_waitlist(client, 'COENG')
        assert len(appointments['resolved']) == 0
        assert len(appointments['unresolved']) > 2
        for index, appointment in enumerate(appointments['unresolved']):
            assert appointment['status'] in ('reserved', 'waiting')

    def test_l_and_s_scheduler_waitlist(self, app, client, fake_auth):
        """L&S scheduler can only see L&S unresolved appointments."""
        fake_auth.login(l_s_college_scheduler_uid)
        dept_code = 'QCADV'
        appointments = self._get_waitlist(client, dept_code)
        assert len(appointments['unresolved']) >= 2
        assert len(appointments['resolved']) == 0
        for appointment in appointments['unresolved']:
            assert appointment['deptCode'] == dept_code

    def test_l_s_college_drop_in_advisor_uid_waitlist(self, app, client, fake_auth):
        """L&S drop-in advisor can only see L&S appointments."""
        fake_auth.login(l_s_college_drop_in_advisor_uid)
        dept_code = 'QCADV'
        appointments = self._get_waitlist(client, dept_code)
        assert len(appointments['unresolved']) >= 2
        assert len(appointments['resolved']) > 0
        for appointment in appointments['unresolved'] + appointments['resolved']:
            assert appointment['deptCode'] == dept_code

    def test_feature_flag(self, client, fake_auth, app):
        """Appointments feature is false."""
        with override_config(app, 'FEATURE_FLAG_ADVISOR_APPOINTMENTS', False):
            fake_auth.login(l_s_college_scheduler_uid)
            self._get_waitlist(client, 'COENG', expected_status_code=401)


class TestMarkAppointmentRead:

    @classmethod
    def _mark_appointment_read(cls, client, appointment_id, expected_status_code=200):
        response = client.post(
            f'/api/appointments/{appointment_id}/mark_read',
            data=json.dumps({'appointmentId': appointment_id}),
            content_type='application/json',
        )
        assert response.status_code == expected_status_code
        return response.json

    def test_mark_read_not_authenticated(self, client):
        """Returns 401 if not authenticated."""
        self._mark_appointment_read(client, 1, expected_status_code=401)

    def test_advisor_read_appointment(self, app, client, fake_auth):
        """L&S advisor reads an appointment."""
        fake_auth.login(l_s_college_scheduler_uid)
        # As scheduler, create appointment
        appointment = AppointmentTestUtil.create_appointment(client, 'QCADV')
        appointment_id = appointment['id']
        client.get('/api/auth/logout')
        # Verify unread by advisor
        uid = l_s_college_advisor_uid
        user_id = AuthorizedUser.get_id_per_uid(uid)
        assert AppointmentRead.was_read_by(user_id, appointment_id) is False
        # Next, log in as advisor and read the appointment
        fake_auth.login(uid)
        api_json = self._mark_appointment_read(client, appointment_id)
        assert api_json['appointmentId'] == appointment_id
        assert api_json['viewerId'] == user_id
        assert AppointmentRead.was_read_by(user_id, appointment_id) is True
        Appointment.delete(appointment_id)


class TestAuthorSearch:

    def test_find_appointment_advisors_by_name(self, client, fake_auth):
        fake_auth.login(coe_advisor_uid)
        response = client.get('/api/appointments/advisors/find_by_name?q=Jo')
        assert response.status_code == 200
        assert len(response.json) == 1
        labels = [s['label'] for s in response.json]
        assert 'Johnny C. Lately' in labels

    def test_feature_flag(self, client, fake_auth, app):
        """Appointments feature is false."""
        with override_config(app, 'FEATURE_FLAG_ADVISOR_APPOINTMENTS', False):
            fake_auth.login(coe_advisor_uid)
            response = client.get('/api/appointments/advisors/find_by_name?q=Jo')
            assert response.status_code == 401
