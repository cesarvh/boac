"""
Copyright ©2018. The Regents of the University of California (Regents). All Rights Reserved.

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

import json

from boac.externals import data_loch
from boac.lib.berkeley import current_term_id
from flask import current_app as app
from flask_login import current_user


"""Provide merged student data from external sources."""


def get_api_json(sids):
    def distill_profile(profile):
        distilled = {key: profile[key] for key in ['uid', 'sid', 'firstName', 'lastName', 'name']}
        if profile.get('athleticsProfile'):
            distilled.update(profile['athleticsProfile'])
        return distilled
    return [distill_profile(profile) for profile in get_full_student_profiles(sids)]


def get_full_student_profiles(sids):
    profile_results = data_loch.get_student_profiles(sids)
    if not profile_results:
        return []
    profiles_by_sid = {row['sid']: json.loads(row['profile']) for row in profile_results}
    profiles = []
    for sid in sids:
        profile = profiles_by_sid.get(sid)
        if profile:
            profiles.append(profile)

    scope = get_student_query_scope()
    if 'UWASC' in scope or 'ADMIN' in scope:
        athletics_profiles = data_loch.get_athletics_profiles(sids)
        for row in athletics_profiles:
            profile = profiles_by_sid.get(row['sid'])
            if profile:
                profile['athleticsProfile'] = json.loads(row['profile'])

    return profiles


def get_summary_student_profiles(sids, term_id=None):
    # TODO It's probably more efficient to store summary profiles in the loch, rather than distilling them
    # on the fly from full profiles.
    profiles = get_full_student_profiles(sids)
    # TODO Many views require no term enrollment information other than a units count. This datum too should be
    # stored in the loch without BOAC having to crunch it.
    if not term_id:
        term_id = current_term_id()
    enrollments_for_term = data_loch.get_enrollments_for_term(term_id, sids)
    enrollments_by_sid = {row['sid']: json.loads(row['enrollment_term']) for row in enrollments_for_term}
    for profile in profiles:
        # Strip SIS details to lighten the API load.
        sis_profile = profile.pop('sisProfile', None)
        if sis_profile:
            profile['cumulativeGPA'] = sis_profile.get('cumulativeGPA')
            profile['cumulativeUnits'] = sis_profile.get('cumulativeUnits')
            profile['level'] = sis_profile.get('level', {}).get('description')
            profile['majors'] = sorted(plan.get('description') for plan in sis_profile.get('plans', []))
        # Add the singleton term.
        term = enrollments_by_sid.get(profile['sid'])
        profile['hasCurrentTermEnrollments'] = False
        if term:
            profile['analytics'] = term.pop('analytics', None)
            profile['term'] = term
            if term['termId'] == current_term_id() and len(term['enrollments']) > 0:
                profile['hasCurrentTermEnrollments'] = True
        # TODO Our existing tests, and possibly the front end, inconsistently expect athletics properties under
        # 'athleticsProfile', and also under the root profile. Clean this up along with the rest of the athletics
        # profile merge.
        if profile.get('athleticsProfile'):
            profile.update(profile['athleticsProfile'])
    return profiles


def get_student_and_terms(uid):
    """Provide external data for student-specific view."""
    student = data_loch.get_student_for_uid(uid)
    if not student:
        return
    profiles = get_full_student_profiles([student['sid']])
    if not profiles or not profiles[0]:
        return
    profile = profiles[0]
    enrollments_for_sid = data_loch.get_enrollments_for_sid(student['sid'])
    profile['enrollmentTerms'] = [json.loads(row['enrollment_term']) for row in enrollments_for_sid]
    profile['hasCurrentTermEnrollments'] = False
    for term in profile['enrollmentTerms']:
        if term['termId'] == current_term_id():
            profile['hasCurrentTermEnrollments'] = len(term['enrollments']) > 0
            break
    return profile


def query_students(
        include_profiles=False,
        coe_advisor_uid=None,
        gpa_ranges=None,
        group_codes=None,
        in_intensive_cohort=None,
        is_active_asc=None,
        levels=None,
        limit=50,
        majors=None,
        offset=0,
        order_by=None,
        sids_only=False,
        unit_ranges=None,
):
    if coe_advisor_uid is not None:
        app.logger.warning(f'Search by coe_advisor_uid is not yet supported; returning empty list.')
        return {
            'sids': [],
            'students': [],
            'totalStudentCount': 0,
        }
    query_tables, query_filter, query_bindings = data_loch.get_students_query(
        group_codes=group_codes,
        gpa_ranges=gpa_ranges,
        levels=levels,
        majors=majors,
        unit_ranges=unit_ranges,
        in_intensive_cohort=in_intensive_cohort,
        is_active_asc=is_active_asc,
    )
    # First, get total_count of matching students
    result = data_loch.safe_execute(f'SELECT DISTINCT(s.sid) {query_tables} {query_filter}', **query_bindings)
    if result is None:
        return None
    summary = {
        'totalStudentCount': len(result),
    }
    if sids_only:
        summary['sids'] = [row['sid'] for row in result]
    else:
        o, o_secondary, o_tertiary, supplemental_query_tables = data_loch.get_students_ordering(
            order_by=order_by,
            group_codes=group_codes,
            majors=majors,
        )
        if supplemental_query_tables:
            query_tables += supplemental_query_tables
        sql = f"""SELECT
            s.sid, MIN({o}), MIN({o_secondary}), MIN({o_tertiary})
            {query_tables}
            {query_filter}
            GROUP BY s.sid
            ORDER BY MIN({o}), MIN({o_secondary}), MIN({o_tertiary})
            OFFSET :offset
        """
        query_bindings['offset'] = offset
        if limit and limit < 100:  # Sanity check large limits
            query_bindings['limit'] = limit
            sql += f' LIMIT :limit'
        result = data_loch.safe_execute(sql, **query_bindings)
        if include_profiles:
            summary['students'] = get_summary_student_profiles([row['sid'] for row in result])
        else:
            summary['students'] = get_api_json([row['sid'] for row in result])
    return summary


def search_for_students(
    include_profiles=False,
    search_phrase=None,
    is_active_asc=None,
    order_by=None,
    offset=0,
    limit=None,
):
    query_tables, query_filter, query_bindings = data_loch.get_students_query(
        search_phrase=search_phrase,
        is_active_asc=is_active_asc,
    )
    o, o_secondary, o_tertiary, supplemental_query_tables = data_loch.get_students_ordering(order_by=order_by)
    if supplemental_query_tables:
        query_tables += supplemental_query_tables
    result = data_loch.safe_execute(f'SELECT DISTINCT(s.sid) {query_tables} {query_filter}', **query_bindings)
    total_student_count = len(result)
    sql = f"""SELECT
        s.sid
        {query_tables}
        {query_filter}
        GROUP BY s.sid
        ORDER BY MIN({o}), MIN({o_secondary}), MIN({o_tertiary})
        OFFSET {offset}
    """
    if limit and limit < 100:  # Sanity check large limits
        sql += f' LIMIT :limit'
        query_bindings['limit'] = limit
    result = data_loch.safe_execute(sql, **query_bindings)
    if include_profiles:
        students = get_summary_student_profiles([row['sid'] for row in result])
    else:
        students = get_api_json([row['sid'] for row in result])
    return {
        'students': students,
        'totalStudentCount': total_student_count,
    }


def get_student_query_scope():
    # Use department membership and admin status to determine what data we can surface about which students.
    if not current_user.is_authenticated:
        return []
    elif current_user.is_admin:
        return ['ADMIN']
    else:
        return [m.university_dept.dept_code for m in current_user.department_memberships]