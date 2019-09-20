import axios from 'axios';
import moment from 'moment-timezone';
import store from '@/store';
import utils from '@/api/api-utils';

export function addStudents(curatedGroupId: number, sids: string[], returnStudentProfiles?: boolean) {
  return axios
    .post(`${utils.apiBaseUrl()}/api/curated_group/students/add`, {
      curatedGroupId: curatedGroupId,
      sids: sids,
      returnStudentProfiles: returnStudentProfiles
    })
    .then(response => {
      const group = response.data;
      store.dispatch('curated/updateCuratedGroup', group);
      return group;
    });
}

export function createCuratedGroup(name: string, sids: string[]) {
  return axios
    .post(`${utils.apiBaseUrl()}/api/curated_group/create`, {
      name: name,
      sids: sids
    })
    .then(function(response) {
      const group = response.data;
      store.dispatch('curated/createCuratedGroup', group);
      return group;
    });
}

export function deleteCuratedGroup(id) {
  return axios
    .delete(`${utils.apiBaseUrl()}/api/curated_group/delete/${id}`, {
      headers: {
        'Content-Type': 'application/json'
      }
    })
    .then(() => {
      store.commit('curated/deleteCuratedGroup', id);
    })
    .then(() => {
      store.dispatch('user/gaCuratedEvent', {
        id: id,
        action: 'delete'
      });
    })
    .catch(error => error);
}

export function downloadCuratedGroupCsv(id: number, name: string) {
  const fileDownload = require('js-file-download');
  const now = moment().format('YYYY-MM-DD_HH-mm-ss');
  return axios
    .get(`${utils.apiBaseUrl()}/api/curated_group/${id}/download_csv`)
    .then(response => fileDownload(response.data, `${name}-students-${now}.csv`), () => null);
}

export function getCuratedGroup(
  id: number,
  orderBy: string,
  offset: number,
  limit: number
) {
  return axios
    .get(`${utils.apiBaseUrl()}/api/curated_group/${id}?orderBy=${orderBy}&offset=${offset}&limit${limit}`)
    .then(response => response.data, () => null);
}

export function getMyCuratedGroupIdsPerStudentId(sid: string) {
  return axios
    .get(`${utils.apiBaseUrl()}/api/curated_groups/my/${sid}`)
    .then(response => response.data, () => null);
}

export function getMyCuratedGroups() {
  return axios
    .get(`${utils.apiBaseUrl()}/api/curated_groups/my`)
    .then(response => response.data, () => null);
}

export function getUsersWithGroups() {
  return axios
    .get(`${utils.apiBaseUrl()}/api/curated_groups/all`)
    .then(response => response.data, () => null);
}

export function removeFromCuratedGroup(groupId, sid) {
  return axios
    .delete(`${utils.apiBaseUrl()}/api/curated_group/${groupId}/remove_student/${sid}`)
    .then(response => {
      const group = response.data;
      store.dispatch('curated/updateCuratedGroup', group);
      return group;
    })
    .then(group => {
      store.dispatch('user/gaCuratedEvent', {
        id: group.id,
        name: group.name,
        action: 'remove_student'
      });
      return group;
    });
}

export function renameCuratedGroup(id, name) {
  return axios
    .post(`${utils.apiBaseUrl()}/api/curated_group/rename`, {id: id, name: name})
    .then(response => {
      const group = response.data;
      store.commit('curated/updateCuratedGroup', group);
      return group;
    })
    .then(group => {
      store.dispatch('user/gaCuratedEvent', {
        id: group.id,
        name: group.name,
        action: 'rename'
      });
      return group;
    })
    .catch(error => error);
}

export function getStudentsWithAlerts(groupId) {
  return axios
    .get(`${utils.apiBaseUrl()}/api/curated_group/${groupId}/students_with_alerts`)
    .then(response => response.data, () => null);
}
