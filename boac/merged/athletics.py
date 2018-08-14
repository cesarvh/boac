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


from boac.externals import data_loch
from boac.merged.student import query_students


def all_team_groups():
    results = data_loch.get_team_groups()
    if not results:
        return []

    def translate_row(row):
        group_code = row['group_code']
        group_name = row['group_name'] + ' (AA)' if group_code.endswith('-AA') else row['group_name']
        return {
            'groupCode': group_code,
            'groupName': group_name,
            'name': group_name,
            'teamCode': row['team_code'],
            'teamName': row['team_name'],
            'totalStudentCount': row['count'],
        }
    return [translate_row(row) for row in results]


def get_team_groups(group_codes):
    results = data_loch.get_team_groups(group_codes=group_codes)
    if not results:
        return []

    def translate_row(row):
        return {
            'groupCode': row['group_code'],
            'groupName': row['group_name'],
            'name': row['group_name'],
            'teamCode': row['team_code'],
            'teamName': row['team_name'],
        }
    return [translate_row(row) for row in results]


def all_teams():
    # TODO: Remove this after we launch new filtered-cohort view
    results = data_loch.get_all_teams()
    if not results:
        return []

    def translate_row(row):
        return {
            'code': row['team_code'],
            'name': row['team_name'],
            'totalStudentCount': row['count'],
        }
    return [translate_row(row) for row in results]


def get_team(team_code, is_active_asc, order_by):
    results = data_loch.get_team_groups(team_code=team_code)
    if not results:
        return None

    team = None
    if len(results):
        team = {
            'teamGroups': [],
        }
        for row in results:
            team['code'] = row['team_code']
            team['name'] = row['team_name']
            team['teamGroups'].append({
                'groupCode': row['group_code'],
                'groupName': row['group_name'],
            })
        group_codes = [group['groupCode'] for group in team['teamGroups']]
        results = query_students(
            group_codes=group_codes,
            is_active_asc=is_active_asc,
            order_by=order_by,
            offset=0,
            limit=None,
        )
        team['students'] = results['students']
        team['totalStudentCount'] = results['totalStudentCount']
    return team
