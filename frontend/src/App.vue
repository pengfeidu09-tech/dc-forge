<script setup>
import { ref } from 'vue'
import {
  ApiOutlined,
  ArrowRightOutlined,
  AuditOutlined,
  DatabaseOutlined,
  MessageOutlined,
  RobotOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import IntelligenceConsole from './components/IntelligenceConsole.vue'

const activeView = ref('tools')

const tools = [
  {
    name: '统一售前工作台',
    description: '需求状态、资料研究、V2 方案、评审发布与客户同步',
    href: '/presales/workbench',
    icon: AuditOutlined,
  },
  {
    name: '客户专属中心',
    description: '客户入口由项目生成，通过飞书机器人或售前工作台获取',
    href: '/presales/workbench',
    icon: MessageOutlined,
  },
  {
    name: '案例知识库与 MCP',
    description: '维护可复用案例，查询 MCP Tool 目录和知识来源',
    href: '/presales/workbench?view=agent',
    icon: DatabaseOutlined,
  },
  {
    name: '飞书 Agent 配置',
    description: '配置客户与内部 Agent 可使用的 Tool 和 Skill',
    href: '/presales/workbench?view=agent',
    icon: SettingOutlined,
  },
]
</script>

<template>
  <a-layout class="internal-shell">
    <a-layout-sider class="internal-sidebar" :width="232">
      <div class="internal-brand">
        <span><RobotOutlined /></span>
        <div><strong>DC FORGE</strong><small>内部工具</small></div>
      </div>
      <a-menu :selected-keys="[activeView]" theme="dark" mode="inline">
        <a-menu-item key="tools" @click="activeView = 'tools'">
          <template #icon><ApiOutlined /></template>
          工具目录
        </a-menu-item>
        <a-menu-item key="console" @click="activeView = 'console'">
          <template #icon><RobotOutlined /></template>
          智能引擎控制台
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout class="internal-main">
      <a-layout-header class="internal-header">
        <div><small>INTERNAL OPERATIONS</small><strong>{{ activeView === 'tools' ? '内部工具目录' : '智能引擎控制台' }}</strong></div>
        <a-tag color="default">不包含内置业务数据</a-tag>
      </a-layout-header>

      <a-layout-content v-if="activeView === 'tools'" class="internal-content">
        <a-alert
          type="info"
          show-icon
          message="业务数据由服务端数据库提供"
          description="此页面只提供工具入口。没有数据库记录时，业务工作台应显示空状态。"
        />

        <section class="tool-directory">
          <header><span>WORKSPACES</span><h1>业务与 Agent 工具</h1></header>
          <a-list :data-source="tools" class="tool-list">
            <template #renderItem="{ item }">
              <a-list-item>
                <a :href="item.href" class="tool-link">
                  <span class="tool-link__icon"><component :is="item.icon" /></span>
                  <span class="tool-link__copy"><strong>{{ item.name }}</strong><small>{{ item.description }}</small></span>
                  <ArrowRightOutlined class="tool-link__arrow" />
                </a>
              </a-list-item>
            </template>
          </a-list>
        </section>
      </a-layout-content>

      <a-layout-content v-else class="internal-console-wrap">
        <IntelligenceConsole />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>
