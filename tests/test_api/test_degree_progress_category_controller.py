"""
Copyright ©2021. The Regents of the University of California (Regents). All Rights Reserved.

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
import json

from boac import std_commit
from boac.models.authorized_user import AuthorizedUser
from boac.models.degree_progress_template import DegreeProgressTemplate
from boac.models.degree_progress_unit_requirement import DegreeProgressUnitRequirement
import pytest

coe_advisor_read_only_uid = '6972201'
coe_advisor_read_write_uid = '1133399'
qcadv_advisor_uid = '53791'


@pytest.fixture()
def mock_template():
    user = AuthorizedUser.find_by_uid(coe_advisor_read_write_uid)
    marker = datetime.now().timestamp()
    return DegreeProgressTemplate.create(
        advisor_dept_codes=['COENG'],
        created_by=user.id,
        degree_name=f'I am a mock template, made for a mock category ({marker})',
    )


class TestCreateDegreeCategory:
    """Degree Progress Category Creation."""

    def test_anonymous(self, client):
        """Denies anonymous user."""
        _api_create_category(
            client,
            category_type='Category',
            name='Anonymous hack!',
            parent_category_id=1,
            position=1,
            template_id=1,
            expected_status_code=401,
        )

    def test_unauthorized(self, client, fake_auth):
        """Denies unauthorized user."""
        fake_auth.login(coe_advisor_read_only_uid)
        _api_create_category(
            client,
            category_type='Category',
            name='Unauthorized hack!',
            parent_category_id=1,
            position=2,
            template_id=1,
            expected_status_code=401,
        )

    def test_create_category(self, client, fake_auth, mock_template):
        """Authorized user can create a category."""
        fake_auth.login(coe_advisor_read_write_uid)
        parent = _api_create_category(
            client,
            category_type='Category',
            name='I am the sun',
            position=1,
            template_id=mock_template.id,
        )
        api_json = _api_create_category(
            client,
            category_type='Subcategory',
            name='I am the rain',
            parent_category_id=parent['id'],
            position=1,
            template_id=mock_template.id,
        )
        assert api_json['id']
        assert api_json['categoryType'] == 'Subcategory'
        assert api_json['name'] == 'I am the rain'
        assert api_json['parentCategoryId'] == parent['id']
        assert api_json['position'] == 1
        assert api_json['templateId'] == mock_template.id


class TestDeleteCategory:

    def test_not_authenticated(self, client):
        """Denies anonymous user."""
        assert client.delete('/api/degree/category/1').status_code == 401

    def test_unauthorized(self, client, fake_auth):
        """Denies unauthorized user."""
        fake_auth.login(qcadv_advisor_uid)
        assert client.delete('/api/degree/category/1').status_code == 401

    def test_delete(self, client, fake_auth, mock_template):
        """COE advisor can delete degree category."""
        fake_auth.login(coe_advisor_read_write_uid)
        original_updated_at = mock_template.updated_at
        category = _api_create_category(
            category_type='Category',
            client=client,
            name='Blister in the sun',
            position=3,
            template_id=mock_template.id,
        )
        subcategory = _api_create_category(
            category_type='Subcategory',
            client=client,
            name='Gone Daddy Gone',
            parent_category_id=category['id'],
            position=3,
            template_id=mock_template.id,
        )
        course = _api_create_category(
            category_type='Course Requirement',
            client=client,
            name='Blister in the sun',
            parent_category_id=subcategory['id'],
            position=3,
            template_id=mock_template.id,
        )
        category_id = category['id']
        assert client.delete(f'/api/degree/category/{category_id}').status_code == 200
        # Verify that all were deleted.
        for object_id in (category_id, subcategory['id'], course['id']):
            assert client.get(f'/api/degree/category/{object_id}').status_code == 404
        # Verify update of updated_at
        std_commit(allow_test_environment=True)
        assert DegreeProgressTemplate.find_by_id(mock_template.id).updated_at != original_updated_at


class TestGetTemplateWithCategory:
    """Get Degree Template API."""

    @classmethod
    def _api_get_template(cls, client, template_id, expected_status_code=200):
        response = client.get(f'/api/degree/{template_id}')
        assert response.status_code == expected_status_code
        return response.json

    def test_get_template_categories(self, client, fake_auth, mock_template):
        """Authorized user can get a template and its categories."""
        user = AuthorizedUser.find_by_uid(coe_advisor_read_write_uid)
        fake_auth.login(user.uid)
        category = _api_create_category(
            category_type='Category',
            client=client,
            description='Seeking subcategories for casual companionship.',
            name='Hot metal in the sun',
            position=3,
            template_id=mock_template.id,
        )
        _api_create_category(
            category_type='Course Requirement',
            client=client,
            name='It\'s a lot of face, a lot of crank air',
            parent_category_id=category['id'],
            position=3,
            template_id=mock_template.id,
            units_lower=2.5,
            units_upper=3,
        )
        subcategory = _api_create_category(
            category_type='Subcategory',
            client=client,
            name='Pony in the air',
            parent_category_id=category['id'],
            position=3,
            template_id=mock_template.id,
        )
        unit_requirement = _create_unit_requirement(name='I am requirement.', template_id=mock_template.id, user=user)
        _api_create_category(
            category_type='Course Requirement',
            client=client,
            units_lower=3,
            name='Sooey and saints at the fair',
            parent_category_id=subcategory['id'],
            position=3,
            template_id=mock_template.id,
            unit_requirement_ids=[unit_requirement.id],
        )
        std_commit(allow_test_environment=True)

        api_json = self._api_get_template(client=client, template_id=mock_template.id)
        categories = api_json['categories']
        assert len(categories) == 1
        subcategories = categories[0]['subcategories']
        assert len(subcategories) == 1
        assert subcategories[0]['name'] == 'Pony in the air'

        courses = categories[0]['courseRequirements']
        assert len(courses) == 1
        assert courses[0]['name'] == 'It\'s a lot of face, a lot of crank air'
        assert courses[0]['unitsLower'] == 2.5
        assert courses[0]['unitsUpper'] == 3

        lower_courses = subcategories[0]['courseRequirements']
        assert len(lower_courses) == 1
        lower_course = lower_courses[0]
        assert lower_course['name'] == 'Sooey and saints at the fair'
        assert lower_course['unitsLower'] == 3
        unit_requirements = lower_course['unitRequirements']
        assert len(unit_requirements) == 1
        assert unit_requirements[0]['id']
        assert unit_requirements[0]['name'] == 'I am requirement.'


class TestUpdateDegreeCategory:
    """Update Degree Category API."""

    @classmethod
    def _api_update_category(
            cls,
            category_id,
            client,
            description,
            name,
            parent_category_id,
            expected_status_code=200,
            unit_requirement_ids=(),
            units_lower=None,
            units_upper=None,
    ):
        response = client.post(
            f'/api/degree/category/{category_id}/update',
            data=json.dumps({
                'name': name,
                'categoryId': category_id,
                'description': description,
                'parentCategoryId': parent_category_id,
                'unitRequirementIds': unit_requirement_ids,
                'unitsLower': units_lower,
                'unitsUpper': units_upper,
            }),
            content_type='application/json',
        )
        assert response.status_code == expected_status_code
        return json.loads(response.data)

    def test_anonymous(self, client):
        """Denies anonymous user."""
        self._api_update_category(
            category_id=1,
            client=client,
            description='Vampire Can Mating Oven',
            expected_status_code=401,
            name='Never Go Back',
            parent_category_id=None,
            units_lower=3,
        )

    def test_unauthorized(self, client, fake_auth):
        """Denies unauthorized user."""
        fake_auth.login(qcadv_advisor_uid)
        self._api_update_category(
            category_id=1,
            client=client,
            description='Vampire Can Mating Oven',
            expected_status_code=401,
            name='Seven Languages',
            parent_category_id=None,
            units_lower=3.0,
        )

    def test_update_category(self, client, fake_auth, mock_template):
        """Authorized user can edit a category."""
        user = AuthorizedUser.find_by_uid(coe_advisor_read_write_uid)
        fake_auth.login(user.uid)
        preserve_me = _create_unit_requirement(
            name='initial_unit_requirement #2',
            template_id=mock_template.id,
            user=user,
        )
        initial_unit_requirements = [
            _create_unit_requirement(name='initial_unit_requirement #1', template_id=mock_template.id, user=user),
            preserve_me,
            _create_unit_requirement(name='initial_unit_requirement #3', template_id=mock_template.id, user=user),
        ]
        position = 3
        categories = []
        for index, name in enumerate(['Never Go Back', 'Seven Languages']):
            categories.append(
                _api_create_category(
                    category_type='Category',
                    client=client,
                    name=name,
                    position=position,
                    template_id=mock_template.id,
                    unit_requirement_ids=[u.id for u in initial_unit_requirements],
                ),
            )
        subcategories = []
        parent_category_id = categories[0]['id']
        for index, name in enumerate(['Processional', 'Ice Cream Everyday']):
            subcategories.append(
                _api_create_category(
                    category_type='Subcategory',
                    client=client,
                    name=name,
                    position=position,
                    template_id=mock_template.id,
                    parent_category_id=parent_category_id,
                ),
            )
        std_commit(allow_test_environment=True)

        # We will give subcategory #2 a new parent.
        name = 'Vampire Can Mating Oven'
        new_parent_category_id = categories[1]['id']
        new_unit_requirement = _create_unit_requirement(name='new_requirement #1', template_id=mock_template.id, user=user)
        new_unit_requirement_ids = [new_unit_requirement.id, preserve_me.id]
        target_subcategory_id = subcategories[1]['id']
        self._api_update_category(
            category_id=target_subcategory_id,
            client=client,
            description=None,
            name=name,
            parent_category_id=new_parent_category_id,
            unit_requirement_ids=[new_unit_requirement.id, preserve_me.id],
            units_lower=3,
        )
        std_commit(allow_test_environment=True)

        # Verify the update
        api_json = _api_get_template(client=client, template_id=mock_template.id)
        categories = api_json['categories']
        assert len(categories) == 2
        assert len(categories[0]['subcategories']) == 1
        assert len(categories[1]['subcategories']) == 1
        # Verify change of parent
        updated_subcategory = categories[1]['subcategories'][0]
        assert updated_subcategory['id'] == target_subcategory_id
        assert updated_subcategory['description'] is None
        assert updated_subcategory['name'] == name
        assert updated_subcategory['parentCategoryId'] == new_parent_category_id
        # Verify add/remove of unit requirements
        unit_requirement_id_set = set([u['id'] for u in updated_subcategory['unitRequirements']])
        assert unit_requirement_id_set == set(new_unit_requirement_ids)


def _api_create_category(
        client,
        category_type,
        name,
        position,
        template_id,
        description=None,
        expected_status_code=200,
        parent_category_id=None,
        unit_requirement_ids=(),
        units_lower=None,
        units_upper=None,
):
    response = client.post(
        '/api/degree/category/create',
        data=json.dumps({
            'categoryType': category_type,
            'description': description,
            'name': name,
            'parentCategoryId': parent_category_id,
            'position': position,
            'templateId': template_id,
            'unitRequirementIds': ','.join(str(id_) for id_ in unit_requirement_ids),
            'unitsLower': units_lower,
            'unitsUpper': units_upper,
        }),
        content_type='application/json',
    )
    assert response.status_code == expected_status_code
    return json.loads(response.data)


def _api_get_template(client, template_id, expected_status_code=200):
    response = client.get(f'/api/degree/{template_id}')
    assert response.status_code == expected_status_code
    return response.json


def _create_unit_requirement(name, template_id, user, min_units=3):
    return DegreeProgressUnitRequirement.create(
        created_by=user.id,
        min_units=min_units,
        name=name,
        template_id=template_id,
    )
