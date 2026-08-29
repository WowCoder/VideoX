export interface MembershipPlan {
  id: "free" | "creator" | "studio";
  name: string;
  description: string;
  monthlyPrice: number;
  annualMonthlyPrice: number;
  annualTotal: number;
  processingMinutes: number;
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
    projectLimit: "3 个项目",
    aiScripts: "10 次 AI 脚本 / 月",
    storage: "10 GB 素材空间",
    export: "720p 导出 · 带水印",
    collaboration: "仅限本人使用",
  },
  {
    id: "creator",
    name: "Creator",
    description: "为稳定产出短视频的专业创作者设计",
    monthlyPrice: 99,
    annualMonthlyPrice: 79,
    annualTotal: 948,
    processingMinutes: 3000,
    projectLimit: "20 个项目",
    aiScripts: "100 次 AI 脚本 / 月",
    storage: "100 GB 素材空间",
    export: "1080p 无水印导出",
    collaboration: "优先处理队列",
    recommended: true,
  },
  {
    id: "studio",
    name: "Studio",
    description: "面向小型内容团队和商业视频工作室",
    monthlyPrice: 299,
    annualMonthlyPrice: 239,
    annualTotal: 2868,
    processingMinutes: 10000,
    projectLimit: "不限项目数量",
    aiScripts: "500 次 AI 脚本 / 月",
    storage: "1 TB 素材空间",
    export: "4K 导出与商业授权",
    collaboration: "5 个团队席位",
  },
];

export function membershipPlanFeatures(plan: MembershipPlan): string[] {
  return [
    `${plan.processingMinutes.toLocaleString()} 分钟处理时长 / 月`,
    plan.projectLimit,
    plan.aiScripts,
    plan.storage,
    plan.export,
    plan.collaboration,
  ];
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
