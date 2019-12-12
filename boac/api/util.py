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

from functools import wraps
import json

from boac.api.errors import BadRequestError
from boac.externals.data_loch import get_sis_holds, get_student_profiles
from boac.lib.berkeley import dept_codes_where_advising
from boac.lib.http import response_with_csv_download
from boac.lib.util import join_if_present
from boac.merged import calnet
from boac.merged.advising_note import get_advising_notes
from boac.merged.student import get_term_gpas_by_sid
from boac.models.alert import Alert
from boac.models.appointment import Appointment
from boac.models.curated_group import CuratedGroup
from boac.models.drop_in_advisor import DropInAdvisor
from boac.models.user_login import UserLogin
from dateutil.tz import tzutc
from flask import current_app as app, request
from flask_login import current_user

"""Utility module containing standard API-feed translations of data objects."""


def admin_required(func):
    @wraps(func)
    def _admin_required(*args, **kw):
        is_authorized = current_user.is_authenticated and current_user.is_admin
        if is_authorized or _api_key_ok():
            return func(*args, **kw)
        else:
            app.logger.warning(f'Unauthorized request to {request.path}')
            return app.login_manager.unauthorized()
    return _admin_required


def advisor_required(func):
    @wraps(func)
    def _advisor_required(*args, **kw):
        is_authorized = current_user.is_authenticated \
            and (
                current_user.is_admin
                or _has_role_in_any_department(current_user, 'isAdvisor')
                or _has_role_in_any_department(current_user, 'isDirector')
            )
        if is_authorized or _api_key_ok():
            return func(*args, **kw)
        else:
            app.logger.warning(f'Unauthorized request to {request.path}')
            return app.login_manager.unauthorized()
    return _advisor_required


def scheduler_required(func):
    @wraps(func)
    def _scheduler_required(*args, **kw):
        is_authorized = current_user.is_authenticated \
            and (
                current_user.is_admin
                or current_user.is_drop_in_advisor
                or _has_role_in_any_department(current_user, 'isScheduler')
            )
        if is_authorized or _api_key_ok():
            return func(*args, **kw)
        else:
            app.logger.warning(f'Unauthorized request to {request.path}')
            return app.login_manager.unauthorized()
    return _scheduler_required


def add_alert_counts(alert_counts, students):
    students_by_sid = {student['sid']: student for student in students}
    for alert_count in alert_counts:
        student = students_by_sid.get(alert_count['sid'], None)
        if student:
            student.update({
                'alertCount': alert_count['alertCount'],
            })
    return students


def authorized_users_api_feed(users, sort_by=None, sort_descending=False):
    if not users:
        return ()
    calnet_users = calnet.get_calnet_users_for_uids(app, [u.uid for u in users])
    profiles = []
    for user in users:
        profile = calnet_users[user.uid]
        if not profile:
            continue
        profile['name'] = ((profile.get('firstName') or '') + ' ' + (profile.get('lastName') or '')).strip()
        profile.update({
            'id': user.id,
            'isAdmin': user.is_admin,
            'isBlocked': user.is_blocked,
            'canAccessCanvasData': user.can_access_canvas_data,
            'deletedAt': _isoformat(user.deleted_at),
            'departments': [],
        })
        for m in user.department_memberships:
            profile['departments'].append({
                'code': m.university_dept.dept_code,
                'name': m.university_dept.dept_name,
                'isAdvisor': m.is_advisor,
                'isDirector': m.is_director,
                'isScheduler': m.is_scheduler,
                'automateMembership': m.automate_membership,
            })
        profile['dropInAdvisorStatus'] = [d.to_api_json() for d in user.drop_in_departments]
        user_login = UserLogin.last_login(user.uid)
        profile['lastLogin'] = _isoformat(user_login.created_at) if user_login else None
        profiles.append(profile)
    sort_by = sort_by or 'lastName'
    return sorted(profiles, key=lambda p: (p.get(sort_by) is None, p.get(sort_by)), reverse=sort_descending)


def canvas_course_api_feed(course):
    return {
        'canvasCourseId': course.get('canvas_course_id'),
        'courseName': course.get('canvas_course_name'),
        'courseCode': course.get('canvas_course_code'),
        'courseTerm': course.get('canvas_course_term'),
    }


def canvas_courses_api_feed(courses):
    if not courses:
        return []
    return [canvas_course_api_feed(course) for course in courses]


def drop_in_advisors_for_dept_code(dept_code):
    dept_code = dept_code.upper()
    advisor_assignments = DropInAdvisor.advisors_for_dept_code(dept_code)
    advisors = []
    for a in advisor_assignments:
        advisor = authorized_users_api_feed([a.authorized_user])[0]
        advisor['available'] = a.is_available
        advisors.append(advisor)
    return sorted(advisors, key=lambda u: (u.get('firstName', '').upper(), u.get('lastName', '').upper(), u.get('id')))


def sis_enrollment_class_feed(enrollment):
    return {
        'displayName': enrollment['sis_course_name'],
        'title': enrollment['sis_course_title'],
        'canvasSites': [],
        'sections': [],
    }


def sis_enrollment_section_feed(enrollment):
    section_data = enrollment.get('classSection', {})
    grades = enrollment.get('grades', [])
    grading_basis = enrollment.get('gradingBasis', {}).get('code')
    return {
        'ccn': section_data.get('id'),
        'component': section_data.get('component', {}).get('code'),
        'sectionNumber': section_data.get('number'),
        'enrollmentStatus': enrollment.get('enrollmentStatus', {}).get('status', {}).get('code'),
        'units': enrollment.get('enrolledUnits', {}).get('taken'),
        'gradingBasis': translate_grading_basis(grading_basis),
        'grade': next((grade.get('mark') for grade in grades if grade.get('type', {}).get('code') == 'OFFL'), None),
        'midtermGrade': next((grade.get('mark') for grade in grades if grade.get('type', {}).get('code') == 'MID'), None),
        'primary': False if grading_basis == 'NON' else True,
    }


def put_notifications(student):
    sid = student['sid']
    student['notifications'] = {
        'note': [],
        'alert': [],
        'hold': [],
        'requirement': [],
    }
    student['notifications']['appointment'] = []
    for appointment in Appointment.get_appointments_per_sid(sid) or []:
        student['notifications']['appointment'].append({
            **appointment.to_api_json(current_user.get_id()),
            **{
                'message': appointment.details,
                'type': 'appointment',
            },
        })

    # The front-end requires 'type', 'message' and 'read'. Optional fields: id, status, createdAt, updatedAt.
    for note in get_advising_notes(sid) or []:
        message = note['body']
        student['notifications']['note'].append({
            **note,
            **{
                'message': message.strip() if message else None,
                'type': 'note',
            },
        })
    for alert in Alert.current_alerts_for_sid(viewer_id=current_user.get_id(), sid=sid):
        student['notifications']['alert'].append({
            **alert,
            **{
                'id': alert['id'],
                'read': alert['dismissed'],
                'type': 'alert',
            },
        })
    for row in get_sis_holds(sid):
        hold = json.loads(row['feed'])
        reason = hold.get('reason', {})
        student['notifications']['hold'].append({
            **hold,
            **{
                'createdAt': hold.get('fromDate'),
                'message': join_if_present('. ', [reason.get('description'), reason.get('formalDescription')]),
                'read': True,
                'type': 'hold',
            },
        })
    degree_progress = student.get('sisProfile', {}).get('degreeProgress', {})
    if degree_progress:
        for key, requirement in degree_progress.get('requirements', {}).items():
            student['notifications']['requirement'].append({
                **requirement,
                **{
                    'type': 'requirement',
                    'message': requirement['name'] + ' ' + requirement['status'],
                    'read': True,
                },
            })


def get_note_attachments_from_http_post(tolerate_none=False):
    request_files = request.files
    attachments = []
    for index in range(app.config['NOTES_ATTACHMENTS_MAX_PER_NOTE']):
        attachment = request_files.get(f'attachment[{index}]')
        if attachment:
            attachments.append(attachment)
        else:
            break
    if not tolerate_none and not len(attachments):
        raise BadRequestError('request.files is empty')
    byte_stream_bundle = []
    for attachment in attachments:
        filename = attachment.filename and attachment.filename.strip()
        if not filename:
            raise BadRequestError(f'Invalid file in request form data: {attachment}')
        else:
            byte_stream_bundle.append({
                'name': filename.rsplit('/', 1)[-1],
                'byte_stream': attachment.read(),
            })
    return byte_stream_bundle


def get_template_attachment_ids_from_http_post():
    ids = request.form.get('templateAttachmentIds', [])
    return ids if isinstance(ids, list) else list(filter(None, str(ids).split(',')))


def get_note_topics_from_http_post():
    topics = request.form.get('topics', ())
    return topics if isinstance(topics, list) else list(filter(None, str(topics).split(',')))


def translate_grading_basis(code):
    bases = {
        'CNC': 'C/NC',
        'EPN': 'P/NP',
        'ESU': 'S/U',
        'GRD': 'Letter',
        'LAW': 'Law',
        'PNP': 'P/NP',
        'SUS': 'S/U',
    }
    return bases.get(code) or code


def get_my_curated_groups():
    curated_groups = []
    user_id = current_user.get_id()
    for curated_group in CuratedGroup.get_curated_groups_by_owner_id(user_id):
        api_json = curated_group.to_api_json(include_students=False)
        students = [{'sid': sid} for sid in CuratedGroup.get_all_sids(curated_group.id)]
        students_with_alerts = Alert.include_alert_counts_for_students(
            viewer_user_id=user_id,
            group={'students': students},
            count_only=True,
        )
        api_json['alertCount'] = sum(s['alertCount'] for s in students_with_alerts)
        api_json['totalStudentCount'] = len(students)
        curated_groups.append(api_json)
    return curated_groups


def is_unauthorized_search(filter_keys, order_by=None):
    filter_key_set = set(filter_keys)
    asc_keys = {'inIntensiveCohort', 'isInactiveAsc', 'groupCodes'}
    if list(filter_key_set & asc_keys) or order_by in ['group_name']:
        if not current_user.is_admin and 'UWASC' not in dept_codes_where_advising(current_user):
            return True
    coe_keys = {
        'coeAdvisorLdapUids',
        'coeEthnicities',
        'coeGenders',
        'coePrepStatuses',
        'coeProbation',
        'coeUnderrepresented',
        'isInactiveCoe',
    }
    if list(filter_key_set & coe_keys):
        if not current_user.is_admin and 'COENG' not in dept_codes_where_advising(current_user):
            return True
    return False


def response_with_students_csv_download(sids, fieldnames, benchmark):
    rows = []
    getters = {
        'first_name': lambda profile: profile.get('firstName'),
        'last_name': lambda profile: profile.get('lastName'),
        'sid': lambda profile: profile.get('sid'),
        'email': lambda profile: profile.get('sisProfile', {}).get('emailAddress'),
        'phone': lambda profile: profile.get('sisProfile', {}).get('phoneNumber'),
        'majors': lambda profile: ';'.join(
            [plan.get('description') for plan in profile.get('sisProfile', {}).get('plans', []) if plan.get('status') == 'Active'],
        ),
        'level': lambda profile: profile.get('sisProfile', {}).get('level', {}).get('description'),
        'terms_in_attendance': lambda profile: profile.get('sisProfile', {}).get('termsInAttendance'),
        'expected_graduation_date': lambda profile: profile.get('sisProfile', {}).get('expectedGraduationTerm', {}).get('name'),
        'units_completed': lambda profile: profile.get('sisProfile', {}).get('cumulativeUnits'),
        'term_gpa': lambda profile: profile.get('termGpa'),
        'cumulative_gpa': lambda profile: profile.get('sisProfile', {}).get('cumulativeGPA'),
        'program_status': lambda profile: profile.get('sisProfile', {}).get('academicCareerStatus'),
    }
    term_gpas = get_term_gpas_by_sid(sids, as_dicts=True)
    for student in get_student_profiles(sids=sids):
        profile = student.get('profile')
        profile = profile and json.loads(profile)
        student_term_gpas = term_gpas.get(profile['sid'])
        profile['termGpa'] = student_term_gpas[sorted(student_term_gpas)[-1]] if student_term_gpas else None
        row = {}
        for fieldname in fieldnames:
            row[fieldname] = getters[fieldname](profile)
        rows.append(row)
    benchmark('end')

    def _norm(row, key):
        value = row.get(key)
        return value and value.upper()
    return response_with_csv_download(
        rows=sorted(rows, key=lambda r: (_norm(r, 'last_name'), _norm(r, 'first_name'), _norm(r, 'sid'))),
        filename_prefix='cohort',
        fieldnames=fieldnames,
    )


def _has_role_in_any_department(user, role):
    return next((d for d in user.departments if d[role]), False)


def _api_key_ok():
    auth_key = app.config['API_KEY']
    return auth_key and (request.headers.get('App-Key') == auth_key)


def _isoformat(value):
    return value and value.astimezone(tzutc()).isoformat()
