<template>
  <div>
    <div>
      <b-table-simple
        :id="`column-${position}-courses-of-category-${parentCategory.id}`"
        borderless
        class="mb-0"
        small
      >
        <b-thead class="border-bottom">
          <b-tr class="sortable-table-header text-nowrap">
            <b-th v-if="assignedCourseCount && $currentUser.canEditDegreeProgress" class="th-course-assignment-menu">
              <span class="sr-only">Options to re-assign course</span>
            </b-th>
            <b-th class="pl-0">Course</b-th>
            <b-th class="pl-0 text-right">Units</b-th>
            <b-th v-if="sid">Grade</b-th>
            <b-th v-if="sid">Note</b-th>
            <b-th v-if="!sid" class="px-0">Fulfillment</b-th>
            <b-th v-if="$currentUser.canEditDegreeProgress" class="px-0 sr-only">Actions</b-th>
          </b-tr>
        </b-thead>
        <b-tbody>
          <template v-for="(bundle, index) in categoryCourseBundles">
            <b-tr
              :id="`course-${bundle.category.id}-table-row-${index}`"
              :key="`tr-${index}`"
            >
              <td class="td-name" :class="{'faint-text font-italic': !bundle.course}">
                <div class="d-flex">
                  {{ bundle.name }}
                </div>
              </td>
              <td class="td-units" :class="{'faint-text font-italic': !bundle.course}">
                <font-awesome
                  v-if="getCourseFulfillments(bundle).length"
                  class="fulfillments-icon mr-1"
                  icon="check-circle"
                  size="sm"
                  :title="`Counts towards ${oxfordJoin(getCourseFulfillments(bundle))}.`"
                />
                <font-awesome
                  v-if="isUnitDiff(bundle)"
                  class="changed-units-icon mr-1"
                  icon="info-circle"
                  size="sm"
                  :title="`Updated from ${pluralize('unit', bundle.category.unitsLower)}`"
                />
                <span class="font-size-14">{{ $_.isNil(bundle.units) ? '&mdash;' : bundle.units }}</span>
                <span v-if="isUnitDiff(bundle)" class="sr-only"> (updated from {{ pluralize('unit', bundle.category.unitsLower) }})</span>
              </td>
              <td v-if="sid" class="td-grade">
                <span class="font-size-14 text-nowrap">
                  {{ $_.get(bundle.course, 'grade') }}
                </span>
              </td>
              <td v-if="sid" class="ellipsis-if-overflow td-note" :title="$_.get(bundle.course, 'note')">
                <span class="font-size-14">
                  {{ $_.get(bundle.course, 'note') }}
                </span>
              </td>
              <td
                v-if="!sid"
                class="align-middle font-size-14 td-max-width-0"
                :class="{'faint-text font-italic': !bundle.course}"
                :title="oxfordJoin($_.map(bundle.unitRequirements, 'name'), 'None')"
              >
                <div class="align-items-start d-flex justify-content-between">
                  <div class="ellipsis-if-overflow">
                    <span>
                      {{ oxfordJoin($_.map(bundle.unitRequirements, 'name'), '&mdash;') }}
                    </span>
                  </div>
                  <div v-if="$_.size(bundle.unitRequirements) > 1" class="unit-requirement-count">
                    <span class="sr-only">(Has </span>{{ bundle.unitRequirements.length }}<span class="sr-only"> requirements.)</span>
                  </div>
                </div>
              </td>
            </b-tr>
          </template>
        </b-tbody>
      </b-table-simple>
    </div>
  </div>
</template>

<script>
import DegreeEditSession from '@/mixins/DegreeEditSession'
import Util from '@/mixins/Util'

export default {
  name: 'CoursesTable',
  mixins: [DegreeEditSession, Util],
  props: {
    items: {
      required: true,
      type: Array
    },
    parentCategory: {
      required: true,
      type: Object
    },
    position: {
      required: true,
      type: Number
    }
  },
  data: () => ({
    bundleForDelete: undefined,
    bundleForEdit: undefined
  }),
  computed: {
    assignedCourseCount() {
      let count = 0
      this.$_.each(this.categoryCourseBundles, bundle => bundle.course && !bundle.course.isCopy && count++)
      return count
    },
    categoryCourseBundles() {
      const transformed = []
      this.$_.each(this.items, item => {
        let category
        let course
        if (item.categoryType) {
          category = item
          course = category.courseIds.length ? this.getCourse(category.courseIds[0]) : null
        } else {
          course = item
          category = this.findCategoryById(course.categoryId)
        }
        transformed.push({
          category,
          course,
          name: (course || category).name,
          units: course ? course.units : this.describeCategoryUnits(category),
          unitRequirements: (course || category).unitRequirements
        })
      })
      return transformed
    }
  },
  methods: {
    describeCategoryUnits(category) {
      if (category) {
        const showRange = category.unitsUpper && category.unitsLower !== category.unitsUpper
        return showRange ? `${category.unitsLower}-${category.unitsUpper}` : category.unitsLower
      } else {
        return null
      }
    },
    getCourseFulfillments(bundle) {
      if (bundle.category && bundle.course) {
        const categoryIds = this.$_.map(bundle.category.unitRequirements, 'id')
        const courseIds = this.$_.map(bundle.course.unitRequirements, 'id')
        const intersection = categoryIds.filter(id => courseIds.includes(id))
        return this.$_.map(this.$_.filter(bundle.category.unitRequirements, u => intersection.includes(u.id)), 'name')
      } else {
        return []
      }
    },
    isUnitDiff(bundle) {
      return this.$_.get(bundle.course, 'isCopy') && bundle.course.units !== bundle.category.unitsLower
    },
  }
}
</script>

<style scoped>
table {
  border-collapse: separate;
  border-spacing: 0 0.05em;
}
.changed-units-icon {
  color: #00c13a;
}
.ellipsis-if-overflow {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fulfillments-icon {
  color: #00c13a;
}
.td-grade {
  padding: 0 0.5em 0 0.4em;
  vertical-align: middle;
  width: 50px;
}
.td-name {
  font-size: 14px;
  padding: 0.25em 0 0.25em 0.25em;
  vertical-align: middle;
}
.td-note {
  max-width: 60px;
  padding: 0 0.5em 0 0;
  vertical-align: middle;
  width: 1px;
}
.td-max-width-0 {
  max-width: 0;
}
.td-units {
  text-align: right;
  padding: 0 0.5em 0 0;
  vertical-align: middle;
  white-space: nowrap;
  width: 50px;
}
.unit-requirement-count {
  background-color: #3b7ea5;
  border-radius: 12px;
  color: white;
  height: 20px;
  text-align: center;
  max-width: 20px;
  min-width: 20px;
}
</style>
