"""
Copyright ©2020. The Regents of the University of California (Regents). All Rights Reserved.

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

from boac.api.errors import BadRequestError, ForbiddenRequestError, ResourceNotFoundError
from boac.api.util import advisor_required, authorized_users_api_feed, drop_in_advisors_for_dept_code, scheduler_required
from boac.lib.berkeley import BERKELEY_DEPT_CODE_TO_NAME
from boac.lib.http import tolerant_jsonify
from boac.lib.util import process_input_from_rich_text_editor
from boac.merged.student import get_distilled_student_profiles
from boac.models.appointment import Appointment
from boac.models.appointment_event import appointment_event_type
from boac.models.appointment_read import AppointmentRead
from boac.models.authorized_user import AuthorizedUser
from flask import current_app as app, request, Response
from flask_login import current_user


@app.route('/api/appointments/waitlist/<dept_code>')
@scheduler_required
def get_waitlist(dept_code):
    def _is_current_user_authorized():
        return current_user.is_admin or dept_code in _dept_codes_with_scheduler_privilege()

    dept_code = dept_code.upper()
    if dept_code not in BERKELEY_DEPT_CODE_TO_NAME:
        raise ResourceNotFoundError(f'Unrecognized department code: {dept_code}')
    elif _is_current_user_authorized():
        show_all_statuses = current_user.is_drop_in_advisor or current_user.is_admin
        statuses = appointment_event_type.enums if show_all_statuses else ['reserved', 'waiting']
        unresolved = []
        resolved = []
        for appointment in Appointment.get_waitlist(dept_code, statuses):
            a = appointment.to_api_json(current_user.get_id())
            if a['status'] in ['reserved', 'waiting']:
                unresolved.append(a)
            else:
                resolved.append(a)
        _put_student_profile_per_appointment(unresolved)
        _put_student_profile_per_appointment(resolved)
        return tolerant_jsonify({
            'advisors': drop_in_advisors_for_dept_code(dept_code),
            'waitlist': {
                'unresolved': unresolved,
                'resolved': resolved,
            },
        })
    else:
        raise ForbiddenRequestError(f'You are unauthorized to manage {dept_code} appointments.')


@app.route('/api/appointments/<appointment_id>')
@advisor_required
def get_appointment(appointment_id):
    appointment = Appointment.find_by_id(appointment_id)
    if not appointment:
        raise ResourceNotFoundError('Unknown path')
    api_json = appointment.to_api_json(current_user.get_id())
    _put_student_profile_per_appointment([api_json])
    return tolerant_jsonify(api_json)


@app.route('/api/appointments/<appointment_id>/check_in', methods=['POST'])
@scheduler_required
def appointment_check_in(appointment_id):
    appointment = Appointment.find_by_id(appointment_id)
    if not appointment:
        raise ResourceNotFoundError('Unknown path')
    if appointment.dept_code not in _dept_codes_with_scheduler_privilege():
        raise ForbiddenRequestError(f'You are unauthorized to manage {appointment.dept_code} appointments.')
    if not appointment.status_change_available():
        raise BadRequestError(appointment.to_api_json(current_user.get_id()))
    params = request.get_json()
    advisor_attrs = _advisor_attrs_for_uid(params.get('advisorUid'))
    if not advisor_attrs:
        raise BadRequestError('Appointment reservation requires valid "advisorUid"')
    Appointment.check_in(
        appointment_id=appointment_id,
        checked_in_by=current_user.get_id(),
        advisor_attrs=advisor_attrs,
    )
    return Response(status=200)


@app.route('/api/appointments/<appointment_id>/cancel', methods=['POST'])
@scheduler_required
def cancel_appointment(appointment_id):
    appointment = Appointment.find_by_id(appointment_id)
    if not appointment:
        raise ResourceNotFoundError('Unknown path')
    has_privilege = current_user.is_admin or appointment.dept_code in _dept_codes_with_scheduler_privilege()
    if not has_privilege:
        raise ForbiddenRequestError(f'You are unauthorized to manage {appointment.dept_code} appointments.')
    if not appointment.status_change_available():
        raise BadRequestError(appointment.to_api_json(current_user.get_id()))
    params = request.get_json()
    cancel_reason = params.get('cancelReason', None)
    cancel_reason_explained = params.get('cancelReasonExplained', None)
    Appointment.cancel(
        appointment_id=appointment_id,
        cancelled_by=current_user.get_id(),
        cancel_reason=cancel_reason,
        cancel_reason_explained=cancel_reason_explained,
    )
    return Response(status=200)


@app.route('/api/appointments/<appointment_id>/reopen', methods=['GET'])
@scheduler_required
def reopen_appointment(appointment_id):
    appointment = Appointment.find_by_id(appointment_id)
    if not appointment:
        raise ResourceNotFoundError('Unknown path')
    _set_appointment_to_waiting(appointment)
    return Response(status=200)


@app.route('/api/appointments/<appointment_id>/reserve', methods=['POST'])
@scheduler_required
def reserve_appointment(appointment_id):
    appointment = Appointment.find_by_id(appointment_id)
    if not appointment:
        raise ResourceNotFoundError('Unknown path')
    has_privilege = current_user.is_admin or appointment.dept_code in _dept_codes_with_scheduler_privilege()
    if not has_privilege:
        raise ForbiddenRequestError(f'You are unauthorized to manage appointment {appointment_id}.')
    if not appointment.status_change_available():
        raise BadRequestError(appointment.to_api_json(current_user.get_id()))
    params = request.get_json()
    advisor_attrs = _advisor_attrs_for_uid(params.get('advisorUid'))
    if not advisor_attrs:
        raise BadRequestError('Appointment reservation requires valid "advisorUid"')
    Appointment.reserve(
        appointment_id=appointment_id,
        reserved_by=current_user.get_id(),
        advisor_attrs=advisor_attrs,
    )
    return Response(status=200)


@app.route('/api/appointments/<appointment_id>/unreserve', methods=['POST'])
@scheduler_required
def unreserve_appointment(appointment_id):
    appointment = Appointment.find_by_id(appointment_id)
    if not appointment:
        raise ResourceNotFoundError('Unknown path')
    has_privilege = current_user.is_admin or appointment.dept_code in _dept_codes_with_scheduler_privilege()
    if not has_privilege:
        raise ForbiddenRequestError(f'You are unauthorized to manage appointment {appointment_id}.')
    if appointment.status != 'reserved':
        raise BadRequestError(appointment.to_api_json(current_user.get_id()))
    _set_appointment_to_waiting(appointment)
    return Response(status=200)


@app.route('/api/appointments/<appointment_id>/update', methods=['POST'])
@scheduler_required
def update_appointment(appointment_id):
    appointment = Appointment.find_by_id(appointment_id)
    if not appointment:
        raise ResourceNotFoundError('Unknown path')
    has_privilege = current_user.is_admin or appointment.dept_code in _dept_codes_with_scheduler_privilege()
    if not has_privilege:
        raise ForbiddenRequestError(f'You are unauthorized to manage {appointment.dept_code} appointments.')
    params = request.get_json()
    details = params.get('details', None)
    topics = params.get('topics', None)
    appointment.update(
        details=process_input_from_rich_text_editor(details),
        topics=topics,
        updated_by=current_user.get_id(),
    )
    api_json = appointment.to_api_json(current_user.get_id())
    _put_student_profile_per_appointment([api_json])
    return tolerant_jsonify(api_json)


def _set_appointment_to_waiting(appointment):
    has_privilege = current_user.is_admin or appointment.dept_code in _dept_codes_with_scheduler_privilege()
    if not has_privilege:
        raise ForbiddenRequestError(f'You are unauthorized to manage appointment {appointment.id}.')
    appointment.set_to_waiting(updated_by=current_user.get_id())


@app.route('/api/appointments/create', methods=['POST'])
@scheduler_required
def create_appointment():
    params = request.get_json()
    dept_code = params.get('deptCode', None)
    sid = params.get('sid', None)
    appointment_type = params.get('appointmentType', None)
    topics = params.get('topics', None)
    if not dept_code or not sid or not appointment_type or not len(topics):
        raise BadRequestError('Appointment creation: required parameters were not provided')
    dept_code = dept_code.upper()
    if dept_code not in BERKELEY_DEPT_CODE_TO_NAME:
        raise ResourceNotFoundError(f'Unrecognized department code: {dept_code}')
    if dept_code not in _dept_codes_with_scheduler_privilege():
        raise ForbiddenRequestError(f'You are unauthorized to manage {dept_code} appointments.')
    advisor_attrs = None
    advisor_uid = params.get('advisorUid')
    if advisor_uid:
        advisor_attrs = _advisor_attrs_for_uid(advisor_uid)
        if not advisor_attrs:
            raise BadRequestError('Invalid "advisorUid"')
    appointment = Appointment.create(
        advisor_attrs=advisor_attrs,
        appointment_type=appointment_type,
        created_by=current_user.get_id(),
        dept_code=dept_code,
        details=process_input_from_rich_text_editor(params.get('details', None)),
        student_sid=sid,
        topics=topics,
    )
    AppointmentRead.find_or_create(current_user.get_id(), appointment.id)
    api_json = appointment.to_api_json(current_user.get_id())
    _put_student_profile_per_appointment([api_json])
    return tolerant_jsonify(api_json)


@app.route('/api/appointments/<appointment_id>/mark_read', methods=['POST'])
@advisor_required
def mark_appointment_read(appointment_id):
    return tolerant_jsonify(AppointmentRead.find_or_create(current_user.get_id(), int(appointment_id)).to_api_json())


@app.route('/api/appointments/advisors/find_by_name', methods=['GET'])
@advisor_required
def find_appointment_advisors_by_name():
    query = request.args.get('q')
    if not query:
        raise BadRequestError('Search query must be supplied')
    limit = request.args.get('limit')
    query_fragments = filter(None, query.upper().split(' '))
    advisors = Appointment.find_advisors_by_name(query_fragments, limit=limit)

    def _advisor_feed(a):
        return {
            'label': a.advisor_name,
            'uid': a.advisor_uid,
        }
    return tolerant_jsonify([_advisor_feed(a) for a in advisors])


def _advisor_attrs_for_uid(advisor_uid):
    authorized_user = AuthorizedUser.find_by_uid(advisor_uid)
    if not authorized_user:
        return None
    api_feeds = authorized_users_api_feed([authorized_user])
    if not api_feeds:
        return None
    api_feed = api_feeds[0]
    return {
        'id': authorized_user.id,
        'uid': advisor_uid,
        'name': api_feed['name'],
        'role': api_feed.get('title') or 'Advisor',
        'deptCodes': [d['code'] for d in api_feed.get('departments', [])],
    }


def _dept_codes_with_scheduler_privilege():
    scheduler_dept_codes = [d['code'] for d in current_user.departments if d.get('role') == 'scheduler']
    drop_in_advisor_dept_codes = [d['deptCode'] for d in current_user.drop_in_advisor_departments]
    return scheduler_dept_codes + drop_in_advisor_dept_codes


def _put_student_profile_per_appointment(waitlist):
    if len(waitlist):
        appointments_by_sid = {}
        for appointment in waitlist:
            sid = appointment['student']['sid']
            if sid not in appointments_by_sid:
                appointments_by_sid[sid] = []
            appointments_by_sid[sid].append(appointment)
        distinct_sids = list(appointments_by_sid.keys())
        for student in get_distilled_student_profiles(distinct_sids):
            sid = student['sid']
            for appointment in appointments_by_sid[sid]:
                appointment['student'] = student
