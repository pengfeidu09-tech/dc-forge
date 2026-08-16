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
  <a-layout-sider
    class="sidebar"
    :class="{ 'sidebar--collapsed': collapsed }"
    :collapsed="collapsed"
    :collapsed-width="72"
    :width="264"
    theme="dark"
  >
    <div class="brand">
      <div class="brand__mark"><span></span><span></span><span></span></div>
      <div v-if="!collapsed">
        <strong>DC FORGE</strong>
        <small>Decision Intelligence</small>
      </div>
    </div>

    <a-menu class="main-nav" theme="dark" mode="inline" :selected-keys="['workspace']">
      <a-menu-item key="workspace"><AppIcon name="grid" /><span>方案工作台</span></a-menu-item>
      <a-menu-item key="assets"><AppIcon name="flow" /><span>流程资产</span></a-menu-item>
      <a-menu-item key="data"><AppIcon name="database" /><span>数据中心</span></a-menu-item>
    </a-menu>

    <div v-if="!collapsed" class="project-nav">
      <div class="project-nav__heading">
        <span>项目场景</span>
        <a-badge :count="projects.length" :overflow-count="99" />
      </div>
      <a-input-search v-model:value="query" class="sidebar-search" placeholder="搜索项目..." allow-clear />
      <a-list class="project-list" :data-source="filteredProjects" size="small">
        <template #renderItem="{ item: project }">
          <a-list-item>
            <a-button
              block
              class="project-item"
              :type="project.project_id === selectedId ? 'primary' : 'text'"
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
            </a-button>
          </a-list-item>
        </template>
      </a-list>
    </div>

    <a-button class="import-button" type="primary" ghost block @click="emit('import')">
      <AppIcon name="upload" />
      <span v-if="!collapsed">导入数据</span>
    </a-button>

    <div v-if="!collapsed" class="sidebar-user">
      <a-avatar>AI</a-avatar>
      <div>
        <strong>方案设计师</strong>
        <small>专业工作空间</small>
      </div>
      <a-badge status="success" />
    </div>
  </a-layout-sider>
</template>
