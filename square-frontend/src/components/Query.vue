<!-- Component for the Search Query. The user can enter a question here and change the query options. -->
<template>
  <form v-on:submit.prevent="askQuestion">
    <div class="row">
      <div class="col-md-4 ms-auto">
        <CompareSkills selector-target="qa" v-on:input="changeSelectedSkills" class="border-danger" />
      </div>
      <div class="col-md-4 me-auto mt-4 mt-md-0">
        <div class="bg-light border border-success rounded shadow h-100 p-3">
          <div class="w-100">
            <label for="question" class="form-label">2. Enter you question</label>
            <textarea
                v-model="currentQuestion"
                @keydown.enter.exact.prevent
                class="form-control form-control-lg mb-2"
                style="resize: none; height: calc(48px * 2.25);"
                id="question"
                placeholder="Question"
                required
                :disabled="!minSkillsSelected(1)" />
            <p v-if="currentExamples.length > 0" class="form-label">Or try one of these examples</p>
            <span
                role="button"
                v-for="(example, index) in currentExamples"
                :key="index"
                v-on:click="selectExample(example)"
                class="badge bg-success m-1 text-wrap lh-base">{{ example.query }}</span>
          </div>
        </div>
      </div>
      <div v-if="skillSettings.requiresContext" class="col-md-4 mt-4 mt-md-0">
        <div class="bg-light border border-warning rounded shadow h-100 p-3">
          <div class="w-100">
            <label for="context" class="form-label">3. Provide context</label>
            <textarea
                v-model="inputContext"
                class="form-control mb-2"
                style="resize: none; height: calc(38px * 7);"
                id="context"
                :placeholder="contextPlaceholder"
                required />
            <small class="text-muted">{{ contextHelp }}</small>
          </div>
        </div>
      </div>
    </div>
    <div v-if="failure" class="row">
      <div class="col-md-4 mx-auto mt-4">
        <Alert class="bg-warning" :dismissible="true">An error occurred
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-emoji-frown" viewBox="0 0 16 16">
            <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
            <path d="M4.285 12.433a.5.5 0 0 0 .683-.183A3.498 3.498 0 0 1 8 10.5c1.295 0 2.426.703 3.032 1.75a.5.5 0 0 0 .866-.5A4.498 4.498 0 0 0 8 9.5a4.5 4.5 0 0 0-3.898 2.25.5.5 0 0 0 .183.683zM7 6.5C7 7.328 6.552 8 6 8s-1-.672-1-1.5S5.448 5 6 5s1 .672 1 1.5zm4 0c0 .828-.448 1.5-1 1.5s-1-.672-1-1.5S9.448 5 10 5s1 .672 1 1.5z"/>
          </svg>
        </Alert>
      </div>
    </div>
    <div v-if="minSkillsSelected(1)" class="row">
      <div class="col mt-4">
        <div class="d-grid gap-2 d-md-flex justify-content-md-center">
          <button
              type="submit"
              class="btn btn-danger btn-lg shadow text-white"
              :disabled="waiting">
            <span v-show="waiting" class="spinner-border spinner-border-sm" role="status" />
            &nbsp;Ask your question</button>
        </div>
      </div>
    </div>
  </form>
</template>

<script>
import Vue from 'vue'
import CompareSkills from '../components/CompareSkills'
import Alert from '../components/Alert'

export default Vue.component('query-skills', {
  data() {
    return {
      waiting: false,
      options: {
        selectedSkills: []
      },
      inputQuestion: '',
      inputContext: '',
      failure: false,
      skillSettings: {
        skillType: null,
        requiresContext: false,
        requiresMultipleChoices: 0
      }
    }
  },
  components: {
    CompareSkills,
    Alert
  },
  computed: {
    selectedSkills() {
      return this.options.selectedSkills.filter(skill => skill !== 'None')
    },
    currentQuestion: {
      get: function () {
        return this.inputQuestion
      },
      set: function (newValue) {
        let tmp = newValue.trimEnd().split('\n')
        this.inputQuestion = tmp.splice(0, 1)[0]
        if (tmp.length > 0) {
          this.inputContext = tmp.join('\n')
        }
      }
    },
    currentExamples() {
      // Pseudo random return 3 examples from currently selected skills
      return this.$store.state.availableSkills
          .filter(skill => skill.skill_input_examples !== null
              && skill.skill_input_examples.length > 0
              && this.selectedSkills.includes(skill.id))
          .flatMap(skill => skill.skill_input_examples)
          .sort(() => 0.5 - Math.random())
          .slice(0, 3)
    },
    contextPlaceholder() {
      if (this.skillSettings.requiresMultipleChoices) {
        let choices = this.skillSettings.requiresMultipleChoices
        return `Provide ${choices > 1 ? choices + ' lines' : 'one line'} of context`
      } else {
        return 'No context required'
      }
    },
    contextHelp() {
      let help = 'no'
      if (this.skillSettings.requiresMultipleChoices) {
        let choices = this.skillSettings.requiresMultipleChoices
        help = `${choices > 1 ? choices + ' lines' : 'one line'} of`
      }
      return `Your selected skills require ${help} context.`
    }
  },
  methods: {
    changeSelectedSkills(options, skillSettings) {
      this.options = options
      this.skillSettings = skillSettings
    },
    minSkillsSelected(num) {
      return this.selectedSkills.length >= num
    },
    askQuestion() {
      this.waiting = true
      this.$store.dispatch('query', {
        question: this.inputQuestion,
        inputContext: this.inputContext,
        options: {
          selectedSkills: this.selectedSkills,
          maxResultsPerSkill: this.options.maxResultsPerSkill
        }
      }).then(() => {
        this.failure = false
      }).catch(() => {
        this.failure = true
      }).finally(() => {
        this.waiting = false
      })
    },
    selectExample(example) {
      this.inputQuestion = example.query
      if (this.skillSettings.requiresContext) {
        this.inputContext = example.context
      }
      this.askQuestion()
    }
  }
})
</script>
