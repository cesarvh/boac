<template>
  <b-modal
    id="advising-appointment-check-in"
    v-model="showCreateAppointmentModal"
    body-class="pl-0 pr-0"
    hide-footer
    hide-header
    :no-close-on-backdrop="true"
    @cancel.prevent="cancel"
    @hide.prevent="cancel">
    <div>
      <div class="modal-header">
        <h3 class="ml-2">
          <span aria-live="polite" role="alert"><span class="sr-only">Create new </span>Advising Appointment</span>
        </h3>
      </div>
      <form @submit.prevent="create()">
        <div class="font-weight-500 ml-4 mr-3 mt-2">
          <div>
            <label
              for="appointment-student-input"
              class="font-size-14 input-label text mt-2">
              <span class="sr-only">Select a </span><span class="font-weight-bolder">Student</span>
              <span v-if="!student"> (name or SID)</span>
              <span class="sr-only">(expect auto-suggest based on what you enter)</span>
            </label>
          </div>
          <div v-if="student" class="d-inline-block">
            <div
              id="appointment-student-input"
              class="d-flex pill pill-student text-uppercase text-nowrap"
              :class="{'demo-mode-blur' : user.inDemoMode}">
              <div class="student-label">
                <span class="sr-only">Student: </span> {{ student.label }}
              </div>
              <div class="mb-1 mr-2">
                <b-btn
                  id="appointment-student-remove"
                  variant="link"
                  class="p-0"
                  @click.prevent="student = undefined">
                  <font-awesome icon="times-circle" class="font-size-24 faint-text pl-2" />
                </b-btn>
                <label class="sr-only" for="appointment-student-remove">
                  Remove student
                </label>
              </div>
            </div>
          </div>
          <div v-if="!student">
            <div class="mb-2">
              <Autocomplete
                id="appointment-student"
                :key="resetAutoCompleteKey"
                class="w-75"
                :demo-mode-blur="true"
                :on-esc-form-input="cancelModal"
                :show-add-button="true"
                :source="studentsByNameOrSid"
                @input="addStudent" />
            </div>
          </div>
          <div class="mt-2">
            <AppointmentTopics
              :disabled="isSaving"
              focus-after-topic-add="appointment-details"
              :function-add="addTopic"
              :function-remove="removeTopic"
              :topics="topics" />
          </div>
          <div class="mb-4 mr-3 mt-1">
            <label for="appointment-details" class="font-size-14 input-label text">
              <span class="font-weight-bolder">Additional Information</span>
            </label>
            <div>
              <b-textarea
                id="appointment-details"
                v-model="details"
                rows="4"
                required>
              </b-textarea>
            </div>
          </div>
        </div>
        <div class="modal-footer pl-0 mt-2">
          <b-btn
            id="create-appointment-confirm"
            class="btn-primary-color-override"
            variant="primary"
            :disabled="!student || !topics.length || !trim(details).length"
            @click.prevent="create()">
            Make Appointment
          </b-btn>
          <b-btn
            id="create-appointment-cancel"
            variant="link"
            @click.prevent="cancelModal()">
            Cancel
          </b-btn>
        </div>
      </form>
    </div>
  </b-modal>
</template>

<script>
import AppointmentTopics from "@/components/appointment/AppointmentTopics";
import Autocomplete from '@/components/util/Autocomplete';
import Context from '@/mixins/Context';
import UserMetadata from '@/mixins/UserMetadata';
import Util from '@/mixins/Util';
import Validator from '@/mixins/Validator';
import { findStudentsByNameOrSid } from '@/api/student';

export default {
  name: 'CreateAppointmentModal',
  components: {AppointmentTopics, Autocomplete},
  mixins: [Context, UserMetadata, Util, Validator],
  props: {
    createAppointment: {
      type: Function,
      required: false
    },
    cancel: {
      type: Function,
      required: true
    },
    showModal: {
      type: Boolean,
      required: true
    }
  },
  data: () => ({
    details: '',
    isSaving: false,
    resetAutoCompleteKey: undefined,
    showCreateAppointmentModal: false,
    student: undefined,
    topics: []
  }),
  watch: {
    showModal(value) {
      this.showCreateAppointmentModal = value;
    }
  },
  created() {
    this.reset();
    this.showCreateAppointmentModal = this.showModal;
    this.putFocusNextTick('appointment-student-input');
    this.alertScreenReader(`Create appointment form is open`);
  },
  methods: {
    addStudent(student) {
      if (student) {
        this.student = student;
        this.alertScreenReader(`Student ${this.student.label} selected`);
        this.putFocusNextTick('add-topic-select-list');
      }
    },
    addTopic(topic) {
      this.topics.push(topic);
      this.alertScreenReader(`Topic ${topic} added`);
    },
    cancelModal() {
      this.cancel();
      this.reset();
    },
    create() {
      this.saving = true;
      this.createAppointment(this.details, this.student, this.topics);
      this.showCreateAppointmentModal = false;
      this.saving = false;
      this.reset();
    },
    removeTopic(topic) {
      const index = this.indexOf(this.topics, topic);
      if (index !== -1) {
        this.topics.splice(index, 1);
      }
    },
    reset() {
      this.details = '';
      this.resetAutoCompleteKey = undefined;
    },
    studentsByNameOrSid(query, limit) {
      return new Promise(resolve => findStudentsByNameOrSid(query, limit).then(students => resolve(students)));
    }
  }
};
</script>

<style scoped>
.pill-student {
  height: 32px;
}
.student-label {
  font-size: 14px;
  margin: 2px 4px 0 8px;
}
</style>