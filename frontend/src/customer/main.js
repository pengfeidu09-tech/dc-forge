import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import CustomerEngagementCenter from './CustomerEngagementCenter.vue'
import './customer.css'

createApp(CustomerEngagementCenter).use(Antd).mount('#customer-engagement-app')
