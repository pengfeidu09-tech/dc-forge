import { createApp } from 'vue'
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Empty,
  Form,
  Input,
  Layout,
  List,
  Menu,
  Modal,
  Popover,
  Result,
  Segmented,
  Select,
  Skeleton,
  Space,
  Spin,
  Steps,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
} from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import PresalesWorkbench from './PresalesWorkbench.vue'
import './presales.css'

const app = createApp(PresalesWorkbench)
for (const component of [
  Alert,
  Badge,
  Button,
  Checkbox,
  Empty,
  Form,
  Input,
  Layout,
  List,
  Menu,
  Modal,
  Popover,
  Result,
  Segmented,
  Select,
  Skeleton,
  Space,
  Spin,
  Steps,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
]) {
  app.use(component)
}
app.mount('#presales-app')
