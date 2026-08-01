import { HuntCopilotStrategy } from "./types";

export const fieldLabels: Array<[keyof HuntCopilotStrategy["hard_filters"], string]> = [
  ["require_instagram", "Instagram"],
  ["require_facebook", "Facebook"],
  ["require_email", "邮箱"],
  ["require_phone", "电话"],
  ["require_website", "官网"],
  ["require_address", "地址"],
];

export const openingSteps = [
  "目标：地区、客户类型、JPS 产品、排除对象",
  "重点补全：Instagram、Facebook、邮箱、电话、官网、地址",
  "数量与预算：候选池、最终客户、预检预算、正式预算",
  "执行规则：候选池、实体合并、排序入选规则",
];
