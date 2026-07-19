<script setup>
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  projects: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  collapsed: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'import'])
const query = ref('')

const filteredProjects = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return props.projects
  return props.projects.filter((project) =>
    [project.project_id, project.meta.name, project.meta.industry]
      .join(' ')
      .toLowerCase()
      .includes(keyword),
  )
})
</script>

<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': collapsed }">
    <div class="brand">
      <div class="brand__mark"><span></span><span></span><span></span></div>
      <div v-if="!collapsed">
        <strong>DC FORGE</strong>
        <small>Decision Intelligence</small>
      </div>
    </div>

    <nav class="main-nav" aria-label="主导航">
      <button class="main-nav__item main-nav__item--active">
        <AppIcon name="grid" />
        <span v-if="!collapsed">方案工作台</span>
      </button>
      <button class="main-nav__item">
        <AppIcon name="flow" />
        <span v-if="!collapsed">流程资产</span>
      </button>
      <button class="main-nav__item">
        <AppIcon name="database" />
        <span v-if="!collapsed">数据中心</span>
      </button>
    </nav>

    <div v-if="!collapsed" class="project-nav">
      <div class="project-nav__heading">
        <span>项目场景</span>
        <span class="count-badge">{{ projects.length }}</span>
      </div>
      <label class="sidebar-search">
        <AppIcon name="search" :size="16" />
        <input v-model="query" type="search" placeholder="搜索项目..." />
      </label>
      <div class="project-list">
        <button
          v-for="project in filteredProjects"
          :key="project.project_id"
          class="project-item"
          :class="{ 'project-item--active': project.project_id === selectedId }"
          @click="emit('select', project.project_id)"
        >
          <span class="project-item__source" :class="`source--${project.meta.source.toLowerCase()}`">
            {{ project.meta.source === 'Twitter' ? '𝕏' : 'C' }}
          </span>
          <span class="project-item__copy">
            <strong>{{ project.meta.shortName }}</strong>
            <small>{{ project.meta.industry }}</small>
          </span>
          <AppIcon name="chevron" :size="15" />
        </button>
      </div>
    </div>

    <button class="import-button" @click="emit('import')">
      <AppIcon name="upload" />
      <span v-if="!collapsed">导入数据</span>
    </button>

    <div v-if="!collapsed" class="sidebar-user">
      <div class="avatar">AI</div>
      <div>
        <strong>方案设计师</strong>
        <small>专业工作空间</small>
      </div>
      <span class="online-dot"></span>
    </div>
  </aside>
</template>
