const fs = require('fs').promises;
const path = require('path');
require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const axios = require('axios');
const { OpenAI } = require('openai');
const bcrypt = require('bcryptjs');
const mysql = require('mysql2/promise');
const multer = require('multer');
const app = express();
const { execFile } = require('child_process');
app.use(bodyParser.json());
app.use(express.json());
app.use(express.urlencoded({ extended: false }));
const { exec } = require('child_process');
const util = require('util');
const execAsync = util.promisify(exec);
const SCRIPT_PATH = '/www/wwwroot/www.longevityllmpumc.com/7_22_datlist/ragmodel_select_code.py';
const PDF_GENERATION_PATH = '/www/wwwroot/www.longevityllmpumc.com/PDF_generation/pdfGeneration.py';
const PDF_OUTPUT_DIR = path.join(__dirname, 'generated_pdfs');


//映射表
const DISEASE_DICT = {
  p130700: "甲状腺毒症",
  p130706: "胰岛素依赖型糖尿病",
  p130708: "非胰岛素依赖型糖尿病",
  p130792: "肥胖症",
  p130828: "其他体液、电解质及酸碱平衡紊乱",
  p131288: "高血压性心脏病",
  p131296: "心绞痛",
  p131298: "急性心肌梗死",
  p131306: "慢性缺血性心脏病",
  p131310: "其他肺源性心脏病",
  p131380: "动脉粥样硬化",
  p131848: "血清阳性型类风湿性关节炎",
  p131894: "系统性红斑狼疮",
  p131900: "结缔组织其他系统性病变",
  p132032: "慢性肾功能衰竭",
  p132092: "男性生殖器官其他疾病",
  p132132: "子宫其他非炎症性病变（宫颈除外）",
  changOR: "总健康评分"
};

const RAG_RESULTS = {
  "您患甲状腺毒症的风险": "thyrotoxic_7_4_txt_res",
  "您患胰岛素依赖型糖尿病的风险": "typ1_6_30_txt",
  "您患非胰岛素依赖型糖尿病的风险": "type2_6_30txt",
  "您患肥胖症的风险": "obesity_7_1_txt_res",
  "您患高血压性心脏病的风险": "hpertensi_res",
  "您患心绞痛的风险": "anginapcet_7_1_txt",
  "您患急性心肌梗死的风险": "acutemyoca_7_1_txt_res",
  "您患慢性缺血性心脏病的风险": "chronicisc_res_7_1_txt",
  "您患其他肺源性心脏病的风险": "pulmonaryh_7_1_txt_res",
  "您患动脉粥样硬化的风险": "atherosclerosis_7_1_txt_res",
  "您患系统性红斑狼疮的风险": "systemiclu_7_1_txt_res",
  "您患结缔组织其他系统性病变的风险": "systemic_involvement_of_connective_tissue_7_1_txt_res",
  "您患慢性肾功能衰竭的风险": "chronicren_7_1_txt_res",
  "您患男性生殖器官其他疾病的风险": "disorderso_res"
};

const DISEASE_NAME_MAPPING = {
  // 英文 -> 中文
  "thyroid toxicosis": "甲状腺毒症",
  "insulin-dependent diabetes": "胰岛素依赖型糖尿病",
  "type 1 diabetes": "胰岛素依赖型糖尿病",
  "non-insulin-dependent diabetes": "非胰岛素依赖型糖尿病",
  "type 2 diabetes": "非胰岛素依赖型糖尿病",
  "obesity": "肥胖症",
  "hypertensive heart disease": "高血压性心脏病",
  "angina pectoris": "心绞痛",
  "acute myocardial infarction": "急性心肌梗死",
  "chronic ischemic heart disease": "慢性缺血性心脏病",
  "other pulmonary heart disease": "其他肺源性心脏病",
  "atherosclerosis": "动脉粥样硬化",
  "seropositive rheumatoid arthritis": "血清阳性型类风湿性关节炎",
  "systemic lupus erythematosus": "系统性红斑狼疮",
  "systemic involvement of connective tissue": "结缔组织其他系统性病变",
  "chronic kidney failure": "慢性肾功能衰竭",
  "chronic renal failure": "慢性肾功能衰竭",
  "male genital organ disorders": "男性生殖器官其他疾病",
  "other noninflammatory disorders of uterus": "子宫其他非炎症性病变"
};

const DISEASE_NAME_MAPPING_REVERSE = {};
Object.entries(DISEASE_NAME_MAPPING).forEach(([en, zh]) => {
  if (!DISEASE_NAME_MAPPING_REVERSE[zh]) {
    DISEASE_NAME_MAPPING_REVERSE[zh] = en;
  }
});


const storage = multer.diskStorage({
  destination: '/www/wwwroot/www.longevityllmpumc.com/uploads/',                       // 保存目录
  filename: (req, file, cb) => {
    // 例： 1720685243123_data_test_7_11.xlsx
    const unique = Date.now() + '_' + file.originalname;
    cb(null, unique);
  }
});
const upload = multer({
  storage: storage,
  limits: {
    fileSize: 10 * 1024 * 1024  // 10MB文件大小限制，避免大Excel文件被截断
  }
});

// 配置项
const CONFIG = {
    openai: {
        apiKey: '你的_OPENAI_API_KEY',
        baseURL: 'https://api.openai.com/v1',
        model: 'gpt-3.5-turbo',
    },
    kimi: {
        apiKey: 'sk-vsgXdMGkM6NyvVuxR0dzDO7uPjAv6JyUZQgvveMLxF4o4aKd',
        baseURL: 'https://api.moonshot.cn/v1',
        model: 'kimi-thinking-preview',
        systemMessage: {
            role: 'system',
            content: '你是 一个个人健康管理专家。'
        }
    }
};

// 全局状态
let currentModel = 'kimi';
let kimiMessages = [];
const BASE_PROMPT_PREFIX = 
`你是一位医学背景的AI健康管理专家。

## 语言规则
若用户首次回复使用英文，则全程使用英文交流。

## 交流流程
用户会先提供身体不适症状，你需按以下顺序进行多轮问诊：

### 必问环节（第1-4轮）
1. 饮食结构
2. 运动习惯  
3. 是否患有糖尿病/高血压，当前用药情况
4. 吸烟情况

### 自由问诊环节（3-5轮）
根据用户长寿得分调整轮数（得分越高轮数越少）。从以下问题中选择：
- 近期关注的健康问题及不适症状（疼痛/疲劳/头晕等）
- 症状出现时间、频率、持续时间
- 体重变化、睡眠质量、大小便情况
- 饮食细节：进餐规律、主食类型、蔬果摄入量、蛋白质来源、烹饪用油、零食甜饮料频率、食物过敏、保健品使用、饮酒习惯
- 作息规律：入睡/起床时间、夜醒频率、工作时间、午休习惯、精力状态
- 运动详情：频率/时长/类型（有氧/力量）、心率变化、日常步数、久坐时间、通勤方式
- 情绪与压力：情绪基调、持续低落情况、压力来源、解压方式
- 既往病史、手术史、用药情况
- 生活环境：空气质量、饮用水源、烹饪方式

问诊结束后，无论用户回答什么，立即进入建议输出流程。

## 注意事项
- 以人类医生口吻交流，避免暴露AI身份（如"当前处于XX流程"）
- 严格按轮次提问，不多问不少问
- 结合初始症状与问诊结果综合判断

患者疾病风险信息如下：`;

const BASE_PROMPT_SUFFIX_WITH_COT = `
## 输出格式要求

### 风险等级说明
- 高(86-100分) = 患病风险低
- 中等(60-85分) = 患病风险中等  
- 低(0-60分) = 患病风险高

### 建议输出格式（严格遵守）
！所有！被判断为中风险和高风险的，**即分数只要实在86分以下的，都要进行输出！**
对于所有的**中高风险**疾病，必须按以下格式输出：

**开头固定格式：**
您患___的风险较___

**建议格式（至少3条）：**
[1]建议内容；|推理：结合用户XXX情况，因为...所以...
[2]建议内容；|推理：基于您的XXX指标...因此...
[3]建议内容；|推理：考虑到XXX因素...需要...

**格式要点：**
- 必须以"您患___的风险"开头（一字不差）
- 每条建议用 [数字] 开始，用 ； 结尾
- 用 | 分隔建议与推理
- 推理必须结合用户具体回复内容
- 每条建议需换行

**完整示例：**
若系统性红斑狼疮评分为[低]：

您患系统性红斑狼疮的风险较高

[1]注意防晒，避免紫外线照射；|推理：您提到经常需要室外站岗，而紫外线是系统性红斑狼疮的重要诱发因素，可能导致病情加重和皮损恶化
[2]保持免疫力稳定，避免使用可能诱发免疫异常的药物或补品；|推理：系统性红斑狼疮是自身免疫性疾病，免疫系统紊乱是其核心病理机制，维持免疫平衡可降低发病风险
[3]避免过度劳累，保证充足休息；|推理：您当前的工作强度较大，而疲劳会削弱免疫调节能力，增加疾病发作风险

注意，所有86分以下，即中风险和高风险的疾病，一定都要严格按以上格式输出
---

## 报告结构（使用Markdown格式）

在给出所有建议前，先输出：
**-----最终建议反馈-----**

然后按以下结构输出：

## 个性化健康管理建议报告

### 整体概述
（综合评估用户健康状况）

### 详细分析

#### 1. 饮食习惯分析
（分析用户饮食结构、营养摄入情况）

#### 2. 运动习惯分析  
（分析用户运动频率、强度、类型）

### 个性化建议
（按疾病风险从高到低给出建议，严格使用上述格式）
（涵盖：饮食习惯、运动规律、作息规律、心理健康等方面）

### 总结与鼓励
（鼓励用户关注健康，说明如有疑问可进一步咨询）`;


let currentPrompt = BASE_PROMPT_PREFIX + '{{DISEASE_RISK}}' + BASE_PROMPT_SUFFIX_WITH_COT;


async function translateToChinese(englishText) {
  try {
    const diseaseList = Object.entries(DISEASE_NAME_MAPPING)
      .map(([en, zh]) => `${en} = ${zh}`)
      .join('\n');

    const messages = [{
      role: 'system',
      content: `你是一个专业的医学翻译。请将以下英文健康报告翻译成中文，必须严格遵循以下格式要求：

【关键格式要求】
1. 疾病风险描述必须翻译为："您患[疾病名]的风险较高/较低/中等"
   例如：Your risk of thyroid toxicosis is HIGH → 您患甲状腺毒症的风险较高
   
2. 建议部分必须保持[1][2]编号格式，分号和竖线必须保留：
   [1]建议内容；|推理：推理内容
   [2]建议内容；|推理：推理内容
   
3. 如果英文文本包含类似结构但格式不对，请重新组织为上述格式
   例如输入：Your risk of diabetes is HIGH. You should exercise more.
   输出：您患非胰岛素依赖型糖尿病的风险较高
        [1]增加运动量；|推理：规律运动有助于控制血糖水平

4. 疾病名称必须使用以下对照表：
${diseaseList}

5. 风险等级映射：
   HIGH → 较高
   MEDIUM → 中等  
   LOW → 较低

6. 保留"-----最终建议反馈----"这样的标记

【示例】
输入：Your risk of systemic lupus erythematosus is HIGH. Avoid UV exposure.
输出：您患系统性红斑狼疮的风险较高
     [1]注意防晒，避免紫外线；|推理：紫外线是系统性红斑狼疮的重要诱发因素

现在请翻译以下内容：`
    }, {
      role: 'user',
      content: englishText
    }];

    const completion = await kimiClient.chat.completions.create({
      model: CONFIG.kimi.model,
      messages: messages,
      temperature: 0.1, // 降低温度，让输出更确定
      max_tokens: 6000
    });

    return completion.choices[0].message.content;
  } catch (error) {
    console.error('翻译成中文失败:', error);
    return englishText;
  }
}

async function translateToEnglish(chineseReport) {
  try {
    const diseaseList = Object.entries(DISEASE_NAME_MAPPING)
      .map(([en, zh]) => `${zh} = ${en}`)
      .join('\n');

    const messages = [{
      role: 'system',
      content: `You are a professional medical translator. Translate the Chinese health report into English with strict format requirements:

【Critical Format Requirements】
1. Disease risk statements must follow this pattern:
   您患[疾病]的风险较高 → Your risk of [disease] is HIGH
   您患[疾病]的风险中等 → Your risk of [disease] is MEDIUM
   您患[疾病]的风险较低 → Your risk of [disease] is LOW

2. Recommendations MUST preserve ALL three components:
   [1]建议内容；
   文献支持: DOI信息
   推理依据: 推理内容
   
   MUST translate to:
   [1] Recommendation text;
   Literature Support: DOI information
   Reasoning: Reasoning text

3. CRITICAL: Do NOT merge "文献支持" and "推理依据" into a single line. Keep them as separate indented lines.

4. Health scores section:
   ### Your health score: → Keep this header exactly as is
   Disease names in scores should use English names
   Format: disease_name: XX/100

5. Disease names must use exact English terms from this mapping: ${diseaseList}

6. Preserve markers like "-----Final Recommendations----"

7. Diet and Exercise Analysis sections:
   #### 1. 饮食习惯分析 → #### 1. Dietary Habits Analysis
   #### 2. 运动习惯分析 → #### 2. Exercise Habits Analysis

IMPORTANT: Always preserve the "### Your health score:" section with all scores listed.`
    }, {
      role: 'user',
      content: chineseReport
    }];

    const completion = await kimiClient.chat.completions.create({
      model: CONFIG.kimi.model,
      messages: messages,
      temperature: 0.1,
      max_tokens: 6000
    });

    return completion.choices[0].message.content;
  } catch (error) {
    console.error('翻译成英文失败:', error);
    return chineseReport;
  }
}


// 初始化 Kimi 客户端
const kimiClient = new OpenAI({
    apiKey: CONFIG.kimi.apiKey,
    baseURL: CONFIG.kimi.baseURL,
});

// MySQL 连接池
const pool = mysql.createPool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
});


const PYTHON = 'python3'; // 或绝对路径：'/www/.../venv/bin/python'
const SCRIPT = path.join(
  __dirname,
  'longevity_app/backend/predict_cli.py'      // ← 你的脚本完整位置
);
const PYTHON_ENV = path.join(__dirname, 'venv/bin/python3');
const LIFESTYLE_RISK_SCRIPT = path.join(__dirname, 'calculate_lifestyle_risk.py');

// 存储用户上传的文件路径（用于生活习惯风险计算）
let currentUserFilePath = null;

async function ensurePdfDir() {
  try {
    await fs.mkdir(PDF_OUTPUT_DIR, { recursive: true });
  } catch (err) {
    console.error('创建PDF目录失败:', err);
  }
}
ensurePdfDir();

// ============ 2. 改进的处理函数 ============
async function processRAGFeedbackWithCOT(answer) {
  // 检查是否包含RAG关键词
  const foundKeys = [];
  let hasRAGContent = false;
  
  for (const [key, dataDir] of Object.entries(RAG_RESULTS)) {
    let start = 0;
    while (true) {
      const idx = answer.indexOf(key, start);
      if (idx < 0) break;
      hasRAGContent = true;
      const ext = answer.substr(idx + key.length, 2);
      foundKeys.push({ key, idx, dataDir, ext });
      start = idx + key.length;
    }
  }
  
  if (!foundKeys.length) {
    return { 
      processedAnswer: answer, 
      isFinalReport: false 
    };
  }

  foundKeys.sort((a, b) => a.idx - b.idx);
  
  const firstKeyIdx = foundKeys[0].idx;
  const prefix = answer.slice(0, firstKeyIdx);
  
  // 解析每个疾病的建议和推理
  const resultsByKey = {};
  for (let i = 0; i < foundKeys.length; i++) {
    const { key, idx } = foundKeys[i];
    const start = idx + key.length + 2;
    const end = (i + 1 < foundKeys.length) ? foundKeys[i + 1].idx : answer.length;
    const segment = answer.slice(start, end);
    
    const items = [];
    // 修改正则表达式以捕获建议和推理部分
    const regex = /\[(\d+)\]([^[\]]*?)(?=[;\[]|$)/g;
    let m;
    while ((m = regex.exec(segment)) !== null) {
      const fullContent = m[2].trim();
      
      // 分离建议和推理（使用竖线分隔）
      const parts = fullContent.split('|');
      const suggestion = parts[0].replace(/[;；]$/, '').trim();
      const reasoning = parts[1] ? parts[1].replace(/^推理[:：]/, '').trim() : '';
      
      items.push({ 
        num: m[1], 
        content: suggestion,
        reasoning: reasoning
      });
    }
    resultsByKey[key] = items;
  }
  
  // 重建文本，包含推理
  let rebuilt = prefix;
  
  for (const { key, dataDir, ext } of foundKeys) {
    rebuilt += key + ext + '\n';
    const items = resultsByKey[key] || [];
    
    for (const { num, content, reasoning } of items) {
      // 添加建议
      rebuilt += `[${num}] ${content};\n`;
      
      // 获取文献支持
      const escaped = content.replace(/(["\\$`])/g, '\\$1');
      const cmd = `${PYTHON_ENV} ${SCRIPT_PATH} "${dataDir}" "${escaped}"`;
      let pyOut;
      try {
        const { stdout } = await execAsync(cmd, {
          cwd: path.dirname(SCRIPT_PATH),
          shell: true,
          maxBuffer: 10 * 1024 * 1024
        });
        pyOut = stdout.trim();
      } catch {
        pyOut = '（检索出错）';
      }
      
      if (pyOut && pyOut !== '（检索出错）') {
        rebuilt += `   文献支持: ${pyOut}\n`;
      }
      
      // 添加推理解释
      if (reasoning) {
        rebuilt += `   推理依据: ${reasoning}\n`;
      }
      
      rebuilt += '\n';
    }
    
    rebuilt += '\n';
  }
  
  return { 
    processedAnswer: rebuilt, 
    isFinalReport: true 
  };
}


function runPredictPython(filePathRel) {
  // 若已是绝对路径则保持，不然拼成绝对
  const filePath = path.isAbsolute(filePathRel)
                   ? filePathRel
                   : path.join(__dirname, filePathRel);

  return new Promise((resolve, reject) => {
    execFile(
      PYTHON,
      [SCRIPT, filePath],
      {
        cwd: path.join(__dirname, 'longevity_app')    // 关键：切到 app 根
      },
      (error, stdout, stderr) => {
        if (stderr) console.error('[PY STDERR]', stderr);
        if (error)  return reject(error);

        try {
          const lastLine = stdout.trim().split('\n').pop();
          const data     = JSON.parse(lastLine);      // 只解析最后一行 JSON
          resolve(data);
        } catch (e) {
          console.error('解析 Python 输出失败:', stdout);
          reject(e);
        }
      }
    );
  });
}


// 新增：计算生活习惯风险的函数（传递文件路径，类似runPredictPython）
async function calculateLifestyleRisk(filePath) {
  return new Promise((resolve, reject) => {
    console.log('[Lifestyle Risk] 调用Python脚本:', filePath);

    execFile(
      PYTHON_ENV2,
      [LIFESTYLE_RISK_SCRIPT, filePath],
      {
        cwd: __dirname,
        maxBuffer: 10 * 1024 * 1024
      },
      (error, stdout, stderr) => {
        if (stderr) {
          console.log('[Lifestyle Risk STDERR]', stderr);
        }
        if (error) {
          console.error('计算生活习惯风险失败:', error);
          return resolve(null); // 失败时返回null，不影响主流程
        }

        try {
          const lines = stdout.trim().split('\n');
          const lastLine = lines[lines.length - 1];
          const result = JSON.parse(lastLine);
          console.log('[Lifestyle Risk] 计算成功，找到', result.lifestyle_risks?.length || 0, '个traits');
          resolve(result);
        } catch (e) {
          console.error('解析生活习惯风险结果失败:', e);
          console.error('Python输出:', stdout);
          resolve(null);
        }
      }
    );
  });
}

// 一次性为多个traits生成建议（批量调用，更快）
async function generateAllLifestyleAdvice(traits) {
  try {
    // 构建包含所有traits的prompt
    const traitsList = traits.map((t, idx) =>
      `${idx + 1}. ${t.trait} (Percentile: ${t.percentile}th, Risk: ${t.health_risk})`
    ).join('\n');

    const prompt = `You are a health advisor. For each of the following 5 lifestyle factors, provide a brief one-sentence health recommendation in English. Keep each recommendation concise, actionable, and professional.

${traitsList}

Please respond in JSON format:
{
  "trait_name_1": "recommendation 1",
  "trait_name_2": "recommendation 2",
  ...
}`;

    console.log(`[Lifestyle Advice] 批量生成5个建议...`);

    const response = await axios.post(
      `${CONFIG.kimi.baseURL}/chat/completions`,
      {
        model: 'moonshot-v1-8k',  // 使用快速模型
        messages: [
          { role: 'system', content: 'You are a health advisor providing brief, actionable lifestyle recommendations in English. Always respond in valid JSON format.' },
          { role: 'user', content: prompt }
        ],
        temperature: 0.7,
        max_tokens: 500,
      },
      {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${CONFIG.kimi.apiKey}`,
        },
        timeout: 20000, // 20秒超时（批量处理需要更多时间）
      }
    );

    const content = response.data.choices[0].message.content.trim();

    // 尝试解析JSON
    let adviceMap = {};
    try {
      // 提取JSON部分（可能包含在```json```代码块中）
      const jsonMatch = content.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        adviceMap = JSON.parse(jsonMatch[0]);
      }
    } catch (e) {
      console.error('[Lifestyle Advice] JSON解析失败，使用fallback建议');
    }

    console.log(`[Lifestyle Advice] 批量生成成功，返回 ${Object.keys(adviceMap).length} 个建议`);
    return adviceMap;

  } catch (error) {
    console.error(`[Lifestyle Advice] 批量生成失败:`, error.message);
    return {}; // 返回空对象，使用fallback
  }
}

// 获取单个trait的建议（从批量结果中提取或使用fallback）
function getAdviceForTrait(traitName, riskLevel, adviceMap) {
  // 尝试从批量生成的建议中查找
  const normalizedName = traitName.toLowerCase().replace(/[^a-z0-9]/g, '_');

  for (const key in adviceMap) {
    const normalizedKey = key.toLowerCase().replace(/[^a-z0-9]/g, '_');
    if (normalizedKey.includes(normalizedName) || normalizedName.includes(normalizedKey)) {
      return adviceMap[key];
    }
  }

  // Fallback建议
  if (riskLevel === 'high') {
    return 'This factor shows elevated levels. Consider consulting with a healthcare professional for personalized guidance.';
  } else if (riskLevel === 'medium') {
    return 'This factor requires attention. Monitor regularly and consider lifestyle modifications for optimal health.';
  } else {
    return 'This factor shows favorable levels. Continue maintaining your current healthy lifestyle habits.';
  }
}

// 格式化生活习惯风险报告（英文版）- 只显示前5个percentile最高的
async function formatLifestyleRiskReport(lifestyleData) {
  if (!lifestyleData || !lifestyleData.success || !lifestyleData.lifestyle_risks) {
    return '';
  }

  const risks = lifestyleData.lifestyle_risks;

  // 按照percentile从高到低排序，取前5个
  const topRisks = risks
    .sort((a, b) => b.percentile - a.percentile)
    .slice(0, 5);

  let report = '\n\n## Lifestyle Risk Assessment\n\n';
  report += 'Based on your protein expression profile, here are the top 5 lifestyle-related health factors that require attention:\n\n';

  // 批量生成所有5个traits的建议（一次API调用）
  const adviceMap = await generateAllLifestyleAdvice(topRisks);

  // 为每个trait添加到报告中
  for (const risk of topRisks) {
    const percentileDecimal = (risk.percentile / 100).toFixed(2);
    const advice = getAdviceForTrait(risk.trait, risk.health_risk, adviceMap);

    report += `**${risk.trait}**\n`;
    report += `- Risk Score: ${risk.final_score.toFixed(4)}\n`;
    report += `- Percentile: ${percentileDecimal}\n`;
    report += `- ${advice}\n\n`;
  }

  return report;
}

// 新增：生成PDF的函数
// 使用系统Python而不是conda环境，避免权限问题
const PYTHON_ENV2 = '/usr/bin/python3';  // 使用完整路径，避免conda环境干扰
async function generatePDF(reportContent, userId) {
  try {
    await fs.mkdir(PDF_OUTPUT_DIR, { recursive: true });

    const ts = Date.now();
    const uid = userId || 'anon';
    const txtFileName = `report_${uid}_${ts}.txt`;
    const txtFilePath = path.join(PDF_OUTPUT_DIR, txtFileName);
    const pdfFileName = `longevity_report_${uid}_${ts}.pdf`;
    const pdfFilePath = path.join(PDF_OUTPUT_DIR, pdfFileName);

    await fs.writeFile(txtFilePath, reportContent, 'utf8');

    const extraText = `Health Management Report - Generated: ${new Date().toLocaleString('en-US')}`;

    // 使用英文版PDF生成器
    await new Promise((resolve, reject) => {
      const args = [PDF_GENERATION_PATH, txtFilePath, pdfFilePath, extraText];
      execFile(
        PYTHON_ENV2,
        args,
        { cwd: path.dirname(PDF_GENERATION_PATH), maxBuffer: 10 * 1024 * 1024 },
        (error, stdout, stderr) => {
          if (stderr) console.warn('[PDF STDERR]', stderr);
          if (error)  return reject(error);
          console.log('[PDF STDOUT]', (stdout || '').trim());
          resolve();
        }
      );
    });

    await fs.access(pdfFilePath);
    await fs.unlink(txtFilePath).catch(() => {});

    if (userId) {
      const conn = await pool.getConnection();
      try {
        await conn.query(
          'INSERT INTO pdf_reports (user_id, pdf_path, created_at) VALUES (?, ?, NOW())',
          [userId, pdfFilePath]
        );
      } finally {
        conn.release();
      }
    }

    return { success: true, pdfPath: pdfFilePath, pdfUrl: `/api/download-pdf/${pdfFileName}` };
  } catch (error) {
    console.error('生成PDF失败:', error);
    return { success: false, error: error.message };
  }
}



// Middleware
app.use(express.static('.'));


function buildDiseaseRiskText(summary) {
  // 注意：scoreToLevel 返回的是 “分数，风险”（括号里显示的“低/中/高”为**风险等级**）
  return Object.entries(summary).map(([k, v]) => {
    const code = k.slice(-7);
    const name = DISEASE_DICT[code] || code;
    return `${name}[${scoreToLevel(v)}]`;
  }).join(' ');
}

// 调用 OpenAI API
async function callOpenAI(question) {
    try {
        const response = await axios.post(
            `${CONFIG.openai.baseURL}/chat/completions`,
            {
                model: CONFIG.openai.model,
                messages: [
                    { role: 'system', content: currentPrompt },
                    { role: 'user', content: question }
                ],
                temperature: 0.1,
            },
            {
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${CONFIG.openai.apiKey}`,
                },
            }
        );
        return response.data.choices[0].message.content;
    } catch (error) {
        console.error('OpenAI API 错误:', error.response.data || error.message);
        return 'OpenAI 暂时无法回答。';
    }
}

// 调用 Kimi API（支持多轮对话）
async function callKimi(question) {
    try {
        if (!kimiMessages) kimiMessages = [];
        
        const userMessage = {
            role: 'user',
            content: (currentPrompt || "") + question
        };
        
        kimiMessages.push({ role: 'user', content: question });
        
        const messages = [{ role: 'system', content: currentPrompt },      // ← 这里是真正的「流程提示词」
            ...kimiMessages.slice(-50)];                       // 保留最近 N 条对话

        
        console.log("发送给Kimi的消息:", messages);
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 600000);
        console.log('[KIMI ►] messages:', messages);
        const completion = await kimiClient.chat.completions.create({
            model: CONFIG.kimi.model || "kimi-thinking-preview",
            messages: messages,
            temperature: 0.25,
            max_tokens: 8500
        }, {
            signal: controller.signal
        });
        console.log('[KIMI ◄] full completion:', completion);
        clearTimeout(timeoutId);
        
        if (!completion.choices[0].message.content) {
            throw new Error("Kimi 返回了空响应");
        }
        
        const assistantMessage = completion.choices[0].message;
        kimiMessages.push(assistantMessage);
        
        if (kimiMessages.length > 50) {
            kimiMessages = kimiMessages.slice(-30);
        }
        
        return assistantMessage.content;
        
    } catch (error) {
        console.error('Kimi API 错误详情:', error);
    
        const status = error.response?.status;
        const message = error.response?.data?.error?.message || error.message;
    
        if (!error.response) {
          return 'Kimi 暂时无法回答，请稍后再试';
        } else if (status === 429) {
          return '请求过于频繁，请稍后再试';
        } else if (status >= 500) {
          return 'Kimi 服务暂时不可用';
        } else {
          // 其它 4xx 错误
          return `Kimi 错误：${message}`;
        }
      }
}

// 1. Add a new function to format health scores
function formatHealthScores(summary) {
  const scoreEntries = Object.entries(summary).map(([k, v]) => {
    const code = k.slice(-7);
    const name = DISEASE_DICT[code] || code;
    // Get English name for the disease
    const englishName = DISEASE_NAME_MAPPING_REVERSE[name] || name;
    return `${englishName}: ${v}/100`;
  });
  
  return `\n\n### Your health score:\n${scoreEntries.join('\n')}\n`;
}

function getTargetDiseases(summary) {
  return Object.entries(summary)
    .filter(([k, v]) => k !== 'changOR' && Number(v) < 86)
    .map(([k]) => {
      const code = k.slice(-7);
      return DISEASE_DICT[code] || code;
    })
    .filter(Boolean);
}

// 2. Store summary globally to use later
let currentSummary = null;

app.post('/api/chat', async (req, res) => {
  try {
    const { question, userId } = req.body;
    
    console.log('收到聊天请求:', { question, userId });
    
    // 1. 获取Kimi的英文回答
    let rawAnswer = await (currentModel === 'openai'
      ? callOpenAI(question)
      : callKimi(question));
    
    console.log('=== AI原始回复 ===');
    console.log(rawAnswer);
    console.log('=================\n');

    // 2. 翻译成中文（用于关键词检测和RAG）
    console.log('开始翻译成中文...');
    const chineseAnswer = await translateToChinese(rawAnswer);
    
    console.log('=== 中文翻译结果 ===');
    console.log(chineseAnswer);
    console.log('===================\n');

    // 3. 使用中文版本进行RAG检索
    console.log('开始RAG处理...');
    const ragResult = await processRAGFeedbackWithCOT(chineseAnswer);
    
    let processedChineseAnswer, isFinalReport;
    if (typeof ragResult === 'object' && ragResult !== null) {
      processedChineseAnswer = ragResult.processedAnswer || chineseAnswer;
      isFinalReport = ragResult.isFinalReport || false;
    } else {
      processedChineseAnswer = chineseAnswer;
      isFinalReport = false;
    }
    
    console.log('=== RAG处理后的中文 ===');
    console.log(processedChineseAnswer);
    console.log('是否为最终报告:', isFinalReport);
    console.log('======================\n');
    
    let pdfInfo = null;
    let finalEnglishReport = rawAnswer;

    // 4. 如果是最终报告，添加健康分数并翻译回英文
    if (isFinalReport) {
      console.log('检测到最终报告，开始添加健康分数...');

      // Add health scores to the Chinese report first
      if (currentSummary) {
        const healthScoresSection = formatHealthScores(currentSummary);
        // Add scores before the final summary section
        const finalMarker = '### 总结与鼓励';
        if (processedChineseAnswer.includes(finalMarker)) {
          processedChineseAnswer = processedChineseAnswer.replace(
            finalMarker,
            healthScoresSection + '\n' + finalMarker
          );
        } else {
          // If no summary section found, add at the end
          processedChineseAnswer += healthScoresSection;
        }
      }

      console.log('开始翻译成英文...');
      finalEnglishReport = await translateToEnglish(processedChineseAnswer);

      // Ensure health scores are in the English report
      if (currentSummary && !finalEnglishReport.includes('Your health score:')) {
        const healthScoresSection = formatHealthScores(currentSummary);
        // Add before "Summary and Encouragement" or at the end
        const summaryMarker = '### Summary and Encouragement';
        if (finalEnglishReport.includes(summaryMarker)) {
          finalEnglishReport = finalEnglishReport.replace(
            summaryMarker,
            healthScoresSection + '\n' + summaryMarker
          );
        } else {
          finalEnglishReport += healthScoresSection;
        }
      }

      // 计算并添加生活习惯风险评估
      if (currentUserFilePath) {
        console.log('开始计算生活习惯风险，文件路径:', currentUserFilePath);
        const lifestyleRiskData = await calculateLifestyleRisk(currentUserFilePath);

        if (lifestyleRiskData && lifestyleRiskData.success) {
          console.log('生活习惯风险计算成功，添加到报告中...');
          const lifestyleReport = await formatLifestyleRiskReport(lifestyleRiskData);

          // 将生活习惯风险报告添加到疾病风险报告之后，总结之前
          const summaryMarker = '### Summary and Encouragement';
          if (finalEnglishReport.includes(summaryMarker)) {
            finalEnglishReport = finalEnglishReport.replace(
              summaryMarker,
              lifestyleReport + '\n' + summaryMarker
            );
          } else {
            // 如果没有找到总结标记，就添加到最后
            finalEnglishReport += lifestyleReport;
          }
        } else {
          console.log('生活习惯风险计算失败或无数据');
        }
      } else {
        console.log('警告：没有用户文件路径，跳过生活习惯风险计算');
      }

      console.log('=== 最终英文报告 ===');
      console.log(finalEnglishReport);
      console.log('===================\n');

      // 生成英文PDF
      pdfInfo = await generatePDF(finalEnglishReport, userId);
      
      if (!pdfInfo.success) {
        console.error('PDF生成失败:', pdfInfo.error);
      } else {
        console.log('PDF生成成功:', pdfInfo.pdfUrl);
      }
    }

    if (!finalEnglishReport || finalEnglishReport.trim() === '') {
      console.error('警告：最终英文回答为空');
      finalEnglishReport = 'Sorry, I am temporarily unable to generate a response. Please try again later.';
    }

    res.json({ 
      answer: finalEnglishReport,
      isFinalReport: isFinalReport,
      pdfInfo: pdfInfo
    });
    
  } catch (error) {
    console.error('聊天API错误:', error);
    res.status(500).json({ 
      error: 'Server error',
      message: error.message 
    });
  }
});

// 新增：PDF下载端点
app.get('/api/download-pdf/:filename', async (req, res) => {
  try {
    const { filename } = req.params;
    
    // 安全性检查：防止路径遍历
    if (filename.includes('..') || filename.includes('/')) {
      return res.status(400).json({ error: '无效的文件名' });
    }
    
    const filePath = path.join(PDF_OUTPUT_DIR, filename);
    
    // 检查文件是否存在
    try {
      await fs.access(filePath);
    } catch {
      return res.status(404).json({ error: '文件不存在' });
    }
    
    // 设置响应头
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
    
    // 发送文件
    res.sendFile(filePath);
    
  } catch (error) {
    console.error('下载PDF失败:', error);
    res.status(500).json({ error: '下载失败' });
  }
});

// 新增：获取用户的历史PDF报告列表
app.get('/api/pdf-history/:userId', async (req, res) => {
  try {
    const { userId } = req.params;
    
    const conn = await pool.getConnection();
    try {
      const [rows] = await conn.query(
        'SELECT id, pdf_path, created_at FROM pdf_reports WHERE user_id = ? ORDER BY created_at DESC LIMIT 10',
        [userId]
      );
      
      const reports = rows.map(row => ({
        id: row.id,
        filename: path.basename(row.pdf_path),
        downloadUrl: `/api/download-pdf/${path.basename(row.pdf_path)}`,
        createdAt: row.created_at
      }));
      
      res.json({ success: true, reports });
      
    } finally {
      conn.release();
    }
    
  } catch (error) {
    console.error('获取PDF历史失败:', error);
    res.status(500).json({ error: '获取历史失败' });
  }
});

// 添加静态文件服务（如果需要直接访问PDF）
app.use('/pdfs', express.static(PDF_OUTPUT_DIR));


// API endpoint to update the prompt
app.post('/api/update-prompt', (req, res) => {
    const { prompt } = req.body;
    if (prompt) {
        currentPrompt = prompt;
        res.json({ success: true, message: '提示词已更新' });
    } else {
        res.status(400).json({ error: '提示词不能为空' });
    }
});

// API endpoint to switch models
app.post('/api/switch-model', (req, res) => {
    const { model } = req.body;
    if (['openai', 'kimi'].includes(model)) {
        currentModel = model;
        res.json({ success: true, message: `已切换到 ${model} 模型` });
    } else {
        res.status(400).json({ error: '无效的模型名称' });
    }
});

// 新增：新建对话API端点
app.post('/api/new-chat', (req, res) => {
    try {
        // 清空对话历史
        kimiMessages = [];
        console.log('对话历史已重置');
        res.json({ success: true, message: '已开始新的对话' });
    } catch (error) {
        res.status(500).json({ 
            error: '创建新会话失败',
            details: error.message
        });
    }
});

app.post('/api/register', async (req, res) => {
  const { phone, password, age, gender } = req.body;
  if (!/^1\d{10}$/.test(phone) || !password) {
    return res.status(400).json({ error: '手机号或密码格式不正确!!!' });
  }

  // 验证年龄和性别
  if (!age || age < 1 || age > 150) {
    return res.status(400).json({ error: '请输入有效的年龄 (1-150)' });
  }
  if (!gender || gender.trim() === '') {
    return res.status(400).json({ error: '性别不能为空' });
  }

  try {
    const [rows] = await pool.query('SELECT id FROM users WHERE phone=?', [phone]);
    if (rows.length) return res.status(409).json({ error: '账号已存在' });

    const hash = await bcrypt.hash(password, 10);
    await pool.query(
      'INSERT INTO users (phone, password, age, gender) VALUES (?, ?, ?, ?)',
      [phone, hash, age, gender]
    );
    res.json({ success: true, message: '注册成功' });
  } catch (e) {
    console.error('注册错误:', e);
    res.status(500).json({ error: '数据库错误' });
  }
});

app.post('/api/login', async (req, res) => {
  const { phone, password } = req.body;
  try {
    const [rows] = await pool.query('SELECT id, password FROM users WHERE phone=?', [phone]);
    if (!rows.length) return res.status(401).json({ error: '账号不存在' });

    const match = await bcrypt.compare(password, rows[0].password);
    if (!match) return res.status(401).json({ error: '密码错误' });

    res.json({ success: true, userId: rows[0].id });
  } catch (e) {
    res.status(500).json({ error: '数据库错误' });
  }
});

// 新增：使用示例文件的API端点
app.post('/api/use-sample-file', async (req, res) => {
  const { userId } = req.body;

  // 服务器上的示例文件路径
  const SAMPLE_FILE_PATH = '/www/wwwroot/www.longevityllmpumc.com/sample_file/date_test_7_11.xlsx';

  const conn = await pool.getConnection();
  try {
    // 检查示例文件是否存在
    try {
      await fs.access(SAMPLE_FILE_PATH);
    } catch {
      return res.status(404).json({ error: '示例文件不存在' });
    }

    // 创建一个临时副本用于处理（避免修改原始示例文件）
    const tempFileName = `sample_${Date.now()}_date_test_7_11.xlsx`;
    const tempFilePath = path.join('/www/wwwroot/www.longevityllmpumc.com/uploads/', tempFileName);
    await fs.copyFile(SAMPLE_FILE_PATH, tempFilePath);

    // 记录到数据库
    const [result] = await conn.query(
      'INSERT INTO user_files (user_id, file_path) VALUES (?, ?)',
      [userId, tempFilePath]
    );
    const srcFileId = result.insertId;

    // CRITICAL: 在疾病预测之前，先复制原始文件用于生活习惯风险计算
    const originalFilePath = tempFilePath.replace('.xlsx', '_original.xlsx');
    await fs.copyFile(tempFilePath, originalFilePath);
    console.log('备份原始文件:', originalFilePath);

    // 使用上传的文件进行疾病预测（这个文件可能会被修改）
    const { resultPath, summary } = await runPredictPython(tempFilePath);

    // 保存备份的原始文件路径（用于生活习惯风险计算）
    currentUserFilePath = originalFilePath;
    console.log('保存原始文件路径用于生活习惯风险计算:', currentUserFilePath);

    // Store summary globally
    currentSummary = summary;
    const mustCover = getTargetDiseases(summary);
    const mustCoverList = mustCover.map((n,i)=>`${i+1}. ${n}`).join('\n');
    const diseaseRiskText = buildDiseaseRiskText(summary);
    const HARD_REQUIRE =
    `\n\n### 必须逐一覆盖的疾病清单（评分<86）
    ${mustCoverList}

    - 上述每个疾病 **都必须** 输出一段：
      - 标题行：您患___的风险较___
      - 至少3条 [编号] 建议，每条都含 "文献支持/推理依据"（若无文献，可空占位）
    - 若任何一个疾病未覆盖，回答 **无效**，请继续生成，直至全部疾病覆盖完成。`;

    currentPrompt = BASE_PROMPT_PREFIX + buildDiseaseRiskText(summary) + BASE_PROMPT_SUFFIX_WITH_COT + HARD_REQUIRE;
    console.log('[DEBUG] 使用示例文件，更新提示词');

    await conn.query(
      `INSERT INTO prediction_results
       (user_id, src_file_path, result_file_path, summary_json)
       VALUES (?,?,?,?)`,
      [userId, tempFilePath, resultPath, JSON.stringify(summary)]
    );

    res.json({
      success: true,
      message: '示例文件加载成功',
      srcFileId,
      resultPath,
      summary
    });
  } catch (e) {
    console.error('使用示例文件错误:', e);
    res.status(500).json({ error: '服务器处理失败' });
  } finally {
    conn.release();
  }
});

app.post('/api/upload', upload.single('file'), async (req, res) => {
  const { userId } = req.body;
  if (!req.file) return res.status(400).json({ error: '未检测到文件' });

  const conn = await pool.getConnection();
  try {
    const [result] = await conn.query(
      'INSERT INTO user_files (user_id, file_path) VALUES (?, ?)',
      [userId, req.file.path]
    );
    const srcFileId = result.insertId;

    // CRITICAL: 在疾病预测之前，先复制原始文件用于生活习惯风险计算
    // 因为疾病预测脚本会修改原始文件，导致生活习惯风险计算读取到错误的数据
    const originalFilePath = req.file.path.replace('.xlsx', '_original.xlsx');
    await fs.copyFile(req.file.path, originalFilePath);
    console.log('备份原始文件:', originalFilePath);

    // 使用上传的文件进行疾病预测（这个文件可能会被修改）
    const { resultPath, summary } = await runPredictPython(req.file.path);

    // 保存备份的原始文件路径（用于生活习惯风险计算）
    // 这个文件保持825列不变，不会被疾病预测脚本修改
    currentUserFilePath = originalFilePath;
    console.log('保存原始文件路径用于生活习惯风险计算:', currentUserFilePath);
    
    // Store summary globally
    currentSummary = summary;
    const mustCover = getTargetDiseases(summary);
    const mustCoverList = mustCover.map((n,i)=>`${i+1}. ${n}`).join('\n');
    const diseaseRiskText = buildDiseaseRiskText(summary);
    const HARD_REQUIRE =
    `\n\n### 必须逐一覆盖的疾病清单（评分<86）
    ${mustCoverList}
    
    - 上述每个疾病 **都必须** 输出一段：
      - 标题行：您患___的风险较___
      - 至少3条 [编号] 建议，每条都含 “文献支持/推理依据”（若无文献，可空占位）
    - 若任何一个疾病未覆盖，回答 **无效**，请继续生成，直至全部疾病覆盖完成。`;
    
    currentPrompt = BASE_PROMPT_PREFIX + buildDiseaseRiskText(summary) + BASE_PROMPT_SUFFIX_WITH_COT + HARD_REQUIRE;
    console.log('[DEBUG] 更新提示词，疾病风险文本:', diseaseRiskText);
    
    await conn.query(
      `INSERT INTO prediction_results
       (user_id, src_file_path, result_file_path, summary_json)
       VALUES (?,?,?,?)`,
      [userId, req.file.path, resultPath, JSON.stringify(summary)]
    );

    res.json({
      success: true,
      message: '文件上传成功',
      srcFileId,
      resultPath,
      summary
    });
  } catch (e) {
    console.error('上传处理错误:', e);
    res.status(500).json({ error: '服务器处理失败' });
  } finally {
    conn.release();
  }
});


// 将分数映射为“风险等级”（注意：分高→风险低）
function scoreToRisk(score) {
  const s = Number
(score);
  if (s <= 60) return '高';     // 风险高
  if (s <= 85) return '中';     // 风险中
  return '低';                  // 风险低（86+）
}

// 按你的需求：返回 “分数，风险”
function scoreToLevel(score) {
  const s = Math.round(Number
(score));
  const risk = scoreToRisk
(s);
  return `${s}，${risk}`;       // 例如 "59，低"（表示分数59，对应风险“低/中/高”）
}


// 不要用 '.'，显式指定静态目录（按你的项目结构改）
app.use(express.static(path.join(__dirname))); // 或 public、dist 等

const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '0.0.0.0';

app.get('/healthz', (req, res) => res.send('ok'));

app.listen(PORT, HOST, () => {
  console.log(`Server listening on http://${HOST}:${PORT}`);
});