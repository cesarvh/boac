<template>
  <div>
    <h2 class="font-size-24 font-weight-bold">Academic Timeline</h2>
    <div class="d-flex justify-content-between flex-wrap ml-2">
      <div>
        <div class="d-flex my-2">
          <div class="align-self-center sr-only">Filter Type:</div>
          <div>
            <b-btn
              id="timeline-tab-all"
              :class="{'tab-active text-white': !filter, 'tab-inactive text-dark': filter}"
              class="tab pl-2 pr-2"
              aria-controls="timeline-messages"
              :aria-selected="!filter"
              variant="link"
              @click="setFilter(null)"
            >
              All
            </b-btn>
          </div>
          <div v-for="type in $_.keys(filterTypes)" :key="type" role="tablist">
            <b-btn
              :id="`timeline-tab-${type}`"
              :class="{
                'tab-active text-white': type === filter && countsPerType[type],
                'tab-inactive text-dark': type !== filter && countsPerType[type],
                'tab-disabled text-muted': !countsPerType[type]
              }"
              aria-controls="timeline-messages"
              :aria-selected="type === filter"
              :disabled="!countsPerType[type]"
              class="tab ml-2 pl-2 pr-2 text-center"
              variant="link"
              @click="setFilter(type)"
            >
              {{ filterTypes[type].tab }}
            </b-btn>
          </div>
        </div>
      </div>
      <div v-if="!$currentUser.isAdmin && $currentUser.canAccessAdvisingData">
        <div>
          <b-btn
            id="new-note-button"
            :disabled="!!mode"
            class="mt-1 mr-2 btn-primary-color-override btn-primary-color-override-opaque"
            variant="primary"
            @click="isCreateNoteModalOpen = true"
          >
            <span class="m-1">
              <font-awesome icon="file-alt" />
              New Note
            </span>
          </b-btn>
        </div>
        <CreateNoteModal
          v-if="isCreateNoteModalOpen"
          :is-batch-feature="false"
          :on-close="onCreateNoteModalClose"
          :sid="student.sid"
        />
      </div>
    </div>
  </div>
</template>

<script>
import Context from '@/mixins/Context'
import CreateNoteModal from '@/components/note/create/CreateNoteModal'
import Util from '@/mixins/Util'

export default {
  name: 'AcademicTimelineHeader',
  mixins: [Context, Util],
  components: {CreateNoteModal},
  props: {
    countsPerType: {
      required: true,
      type: Object
    },
    filter: {
      required: false,
      type: String
    },
    filterTypes: {
      required: true,
      type: Object
    },
    setFilter: {
      required: true,
      type: Function
    },
    student: {
      required: true,
      type: Object
    }
  },
  data: () => ({
    isCreateNoteModalOpen: false
  }),
  methods: {
    onCreateNoteModalClose(note) {
      this.isCreateNoteModalOpen = false
      this.$putFocusNextTick(note && this.$_.includes(['all', 'note'], this.activeTab) ? `timeline-tab-${this.activeTab}-message-0` : 'new-note-button')
    }
  }
}
</script>

<style scoped>
.tab {
  border-radius: 5px;
  font-size: 16px;
  font-weight: 800;
  height: 40px;
}
.tab-active {
  background-color: #555;
}
.tab-active:active,
.tab-active:focus,
.tab-active:hover {
  background-color: #444;
}
.tab-disabled {
  background-color: #ccc;
}
.tab-inactive {
  background-color: #eee;
}
.tab-inactive:hover,
.tab-inactive:hover,
.tab-inactive:hover {
  background-color: #ddd;
}
</style>