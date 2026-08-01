import { openingSteps } from "../constants";

export function OpeningGuide() {
  return (
    <div className="space-y-3 rounded-md bg-background p-4 text-sm text-muted-foreground">
      <div className="space-y-2">
        <p className="font-medium text-foreground">接下来我们会按这四个步骤进行整理搜索策略：</p>
        <ol className="list-decimal space-y-1 pl-5">
          {openingSteps.map((step) => <li key={step}>{step}</li>)}
        </ol>
      </div>
      <p>例如：我需要越南牙科学校和牙科设备经销商，必须有 Instagram、邮箱和电话，最终要 10 个客户，候选池先找 40 个，预算 1 美元，排除普通牙科诊所。</p>
    </div>
  );
}
