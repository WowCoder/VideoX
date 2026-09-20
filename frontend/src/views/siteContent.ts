export interface MembershipPlan {
  id: "free" | "creator" | "pro" | "studio" | "team";
  name: string;
  description: string;
  monthlyPrice: number;
  annualMonthlyPrice: number;
  annualTotal: number;
  processingMinutes: number;
  monthlyCredits: number;
  projectLimit: string;
  aiScripts: string;
  storage: string;
  export: string;
  collaboration: string;
  recommended?: boolean;
}

export interface ShowcaseWork {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  src: string;
  poster: string;
  mediaType: "image" | "video";
}

export interface StartingPoint {
  id: "concept" | "script" | "assets";
  method: "ai-script" | "write-script" | "upload-assets";
  index: string;
  label: string;
  title: string;
  description: string;
}

const asteroidImage = "/media/showcase/asteroid-mission-concept.jpg";
const moonImage = "/media/showcase/moonset-from-orbit.jpg";
const milkyWayImage = "/media/showcase/cinematic/milky-way-kandersteg.webp";

export const membershipPlans: MembershipPlan[] = [
  {
    id: "free",
    name: "Free",
    description: "适合体验 OpenVMA 的个人创作者",
    monthlyPrice: 0,
    annualMonthlyPrice: 0,
    annualTotal: 0,
    processingMinutes: 600,
    monthlyCredits: 300,
    projectLimit: "3 个项目",
    aiScripts: "注册赠送 300 V-Credits",
    storage: "2 GB 素材空间",
    export: "720p 预览 · 带水印",
    collaboration: "仅限本人使用",
  },
  {
    id: "creator",
    name: "Creator",
    description: "为稳定产出短视频的专业创作者设计",
    monthlyPrice: 39,
    annualMonthlyPrice: 33.25,
    annualTotal: 399,
    processingMinutes: 0,
    monthlyCredits: 6000,
    projectLimit: "2 个并发任务",
    aiScripts: "6,000 V-Credits / 月",
    storage: "50 GB 素材空间",
    export: "1080p 无水印导出",
    collaboration: "标准模型与优先队列",
    recommended: true,
  },
  {
    id: "pro",
    name: "Pro",
    description: "为高频产出与更高画质的专业创作者设计",
    monthlyPrice: 99,
    annualMonthlyPrice: 83.25,
    annualTotal: 999,
    processingMinutes: 0,
    monthlyCredits: 18000,
    projectLimit: "4 个并发任务",
    aiScripts: "18,000 V-Credits / 月",
    storage: "200 GB 素材空间",
    export: "1080p / 4K 图片与商业授权",
    collaboration: "高级模型与 7% 充值加成",
  },
  {
    id: "studio",
    name: "Studio",
    description: "面向小型内容团队和商业视频工作室",
    monthlyPrice: 299,
    annualMonthlyPrice: 266.58,
    annualTotal: 3199,
    processingMinutes: 0,
    monthlyCredits: 55000,
    projectLimit: "8 个并发任务",
    aiScripts: "55,000 V-Credits / 月",
    storage: "1 TB 素材空间",
    export: "1080p / 4K 图片与商业授权",
    collaboration: "高级模型与 15% 充值加成 · 3 席位",
  },
  {
    id: "team",
    name: "Team",
    description: "面向多人协作与规模化内容生产团队",
    monthlyPrice: 699,
    annualMonthlyPrice: 624.92,
    annualTotal: 7499,
    processingMinutes: 0,
    monthlyCredits: 130000,
    projectLimit: "16 个并发任务",
    aiScripts: "130,000 V-Credits / 月",
    storage: "2 TB 素材空间",
    export: "高级模型、API 与批量生成",
    collaboration: "25% 充值加成 · 5 席位",
  },
];

export function membershipPlanFeatures(plan: MembershipPlan): string[] {
  const features = [
    `${plan.monthlyCredits.toLocaleString()} V-Credits / 月`,
    plan.projectLimit,
    plan.storage,
    plan.export,
    plan.collaboration,
  ];
  if (!plan.aiScripts.startsWith(`${plan.monthlyCredits.toLocaleString()} V-Credits`)) {
    features.splice(2, 0, plan.aiScripts);
  }
  return features;
}

export const helpCenterCopy = {
  description: "从第一个想法到最终导出，按故事、镜头、素材、声音和成片阶段找到直接可执行的答案。",
};

export const helpFaqs: Array<[string, string]> = [
  ["为什么上传完成后还不能搜索？", "上传只是第一步，素材还需要完成转码、切片、语音识别、视觉理解和索引。素材库会显示当前阶段，变为“可搜索”后即可使用语义检索。"],
  ["关闭页面后任务会停止吗？", "不会。上传、理解、分镜匹配和 AI 生成会继续执行，结果会同步回对应素材、分镜或项目主时间线。"],
  ["一句脚本可以对应多个分镜吗？", "可以。台词作为父级只保留一份，每句脚本下可添加多个拥有独立画面、时长、来源和备注的分镜。"],
  ["如何让不同 AI 镜头里的人物和空间保持一致？", "在脚本编辑器的“全片设定”中锁定人物、物品和空间参考。后续 AI 生图、图生视频与缺失镜头补齐会共同引用这些特征。"],
  ["AI 生成的素材会保存在哪里？", "生成完成后会自动加入当前项目的素材箱，并在素材库中显示来源、生成类型和处理状态。"],
];

export const FEATURED_SHOWCASE_WORKS: ShowcaseWork[] = [
  {
    id: "orbital-archive",
    eyebrow: "DEEP SPACE MISSION / 00:58",
    title: "轨道档案：小行星取样任务",
    description: "以 NASA/JPL 任务概念图为视觉锚点，建立探测器、岩面与深空尺度的硬科幻开场。",
    mediaType: "image",
    src: asteroidImage,
    poster: asteroidImage,
  },
  {
    id: "moonset-orbit",
    eyebrow: "ORBITAL OBSERVATION / 00:32",
    title: "地球薄暮：月牙升过大气边缘",
    description: "真实轨道观测中的月牙与地球大气层，以极简留白呈现安静而宏大的宇宙尺度。",
    mediaType: "image",
    src: moonImage,
    poster: moonImage,
  },
  {
    id: "milky-way-kandersteg",
    eyebrow: "ALPINE NIGHT SKY / 00:46",
    title: "雪线之上：银河横穿阿尔卑斯",
    description: "真实夜空长曝光保留星群、冰川与山体纹理，让银河成为一条横跨地景的叙事光带。",
    mediaType: "image",
    src: milkyWayImage,
    poster: milkyWayImage,
  },
];

export const STARTING_POINTS: StartingPoint[] = [
  { id: "concept", method: "ai-script", index: "01", label: "一个想法", title: "从概念开始", description: "描述题材、观众和情绪，让 AI 先给出可编辑脚本与视觉方向。" },
  { id: "script", method: "write-script", index: "02", label: "一份脚本", title: "导入脚本或文案", description: "粘贴文章、旁白或脚本表格，自动拆成场景与镜头。" },
  { id: "assets", method: "upload-assets", index: "03", label: "一组素材", title: "从已有画面开始", description: "选择图片、视频和声音，让 AI 理解内容并组织第一版故事结构。" },
];
