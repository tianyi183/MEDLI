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
const SCRIPT_PATH = 'ragmodel_select_code.py';
const PDF_GENERATION_PATH = 'pdfGeneration.py';
const PDF_OUTPUT_DIR = path.join(__dirname, 'generated_pdfs');


// Mapping table from disease codes to human-readable labels
const DISEASE_DICT = {
  p130700: "Thyroid toxicosis",
  p130706: "Insulin-dependent diabetes",
  p130708: "Non-insulin-dependent diabetes",
  p130792: "Obesity",
  p130828: "Other fluid, electrolyte, and acid-base disorders",
  p131288: "Hypertensive heart disease",
  p131296: "Angina pectoris",
  p131298: "Acute myocardial infarction",
  p131306: "Chronic ischemic heart disease",
  p131310: "Other pulmonary heart disease",
  p131380: "Atherosclerosis",
  p131848: "Seropositive rheumatoid arthritis",
  p131894: "Systemic lupus erythematosus",
  p131900: "Other systemic connective-tissue disorders",
  p132032: "Chronic kidney failure",
  p132092: "Other male genital organ disorders",
  p132132: "Other non-inflammatory uterine disorders (excluding cervix)",
  changOR: "Overall health score"
};

const RAG_RESULTS = {
  "Your risk of thyroid toxicosis": "thyrotoxic_7_4_txt_res",
  "Your risk of insulin-dependent diabetes": "typ1_6_30_txt",
  "Your risk of non-insulin-dependent diabetes": "type2_6_30txt",
  "Your risk of obesity": "obesity_7_1_txt_res",
  "Your risk of hypertensive heart disease": "hpertensi_res",
  "Your risk of angina pectoris": "anginapcet_7_1_txt",
  "Your risk of acute myocardial infarction": "acutemyoca_7_1_txt_res",
  "Your risk of chronic ischemic heart disease": "chronicisc_res_7_1_txt",
  "Your risk of other pulmonary heart disease": "pulmonaryh_7_1_txt_res",
  "Your risk of atherosclerosis": "atherosclerosis_7_1_txt_res",
  "Your risk of systemic lupus erythematosus": "systemiclu_7_1_txt_res",
  "Your risk of other systemic connective-tissue disorders": "systemic_involvement_of_connective_tissue_7_1_txt_res",
  "Your risk of chronic kidney failure": "chronicren_7_1_txt_res",
  "Your risk of other male genital disorders": "disorderso_res"
};

const DISEASE_NAME_MAPPING = {
  // English -> English (kept for compatibility with downstream mapping helpers)
  "thyroid toxicosis": "Thyroid toxicosis",
  "insulin-dependent diabetes": "Insulin-dependent diabetes",
  "type 1 diabetes": "Type 1 diabetes",
  "non-insulin-dependent diabetes": "Non-insulin-dependent diabetes",
  "type 2 diabetes": "Type 2 diabetes",
  "obesity": "Obesity",
  "hypertensive heart disease": "Hypertensive heart disease",
  "angina pectoris": "Angina pectoris",
  "acute myocardial infarction": "Acute myocardial infarction",
  "chronic ischemic heart disease": "Chronic ischemic heart disease",
  "other pulmonary heart disease": "Other pulmonary heart disease",
  "atherosclerosis": "Atherosclerosis",
  "seropositive rheumatoid arthritis": "Seropositive rheumatoid arthritis",
  "systemic lupus erythematosus": "Systemic lupus erythematosus",
  "systemic involvement of connective tissue": "Other systemic connective-tissue disorder",
  "chronic kidney failure": "Chronic kidney failure",
  "chronic renal failure": "Chronic kidney failure",
  "male genital organ disorders": "Other male genital organ disorder",
  "other noninflammatory disorders of uterus": "Other non-inflammatory uterine disorder"
};

const DISEASE_NAME_MAPPING_REVERSE = {};
Object.entries(DISEASE_NAME_MAPPING).forEach(([en, zh]) => {
  if (!DISEASE_NAME_MAPPING_REVERSE[zh]) {
    DISEASE_NAME_MAPPING_REVERSE[zh] = en;
  }
});


const storage = multer.diskStorage({
  destination: 'uploads/', // directory for uploaded files
  filename: (req, file, cb) => {
    // Example: 1720685243123_data_test_7_11.xlsx
    const unique = Date.now() + '_' + file.originalname;
    cb(null, unique);
  }
});
const upload = multer({
  storage,
  limits: {
    fileSize: 10 * 1024 * 1024, // limit uploads to 10 MB to avoid truncated spreadsheets
  },
});

// Configuration (sensitive values are supplied via environment variables)
const CONFIG = {
    openai: {
        apiKey: process.env.OPENAI_API_KEY || 'YOUR_OPENAI_API_KEY', // replace with your OpenAI token
        baseURL: 'https://api.openai.com/v1',
        model: 'gpt-3.5-turbo',
    },
    kimi: {
        apiKey: process.env.KIMI_API_KEY || 'YOUR_KIMI_API_KEY', // replace with your Kimi token
        baseURL: 'https://api.moonshot.cn/v1',
        model: 'kimi-thinking-preview',
        systemMessage: {
            role: 'system',
            content: 'You are a personal health-management specialist.'
        }
    }
};

// Global conversation state for the Kimi-based dialogue
let currentModel = 'kimi';
let kimiMessages = [];
const BASE_PROMPT_PREFIX =
`You are an AI health-management specialist with formal medical training.

## Language Rules
If the userâ€™s first response is in English, keep the entire conversation in English.

## Interview Flow
The user begins by describing symptoms. Ask questions in this order:

### Mandatory rounds (1-4)
1. Diet structure
2. Exercise habits
3. Diabetes/hypertension status and current medications
4. Smoking status

### Free-form rounds (3-5)
Adjust the number of rounds based on the longevity score (higher score â†?fewer rounds). Choose among:
- Current health concerns and symptoms (pain, fatigue, dizziness, etc.)
- Symptom onset time, frequency, and duration
- Weight changes, sleep quality, bowel/bladder status
- Diet details: meal routine, staple foods, fruit/vegetable intake, protein sources, cooking oil, snacks/sweet drinks, food allergies, supplement usage, alcohol consumption
- Daily routine: sleep/wake times, nighttime awakenings, working hours, nap habits, energy level
- Exercise details: frequency/duration/type (cardio vs. strength), heart-rate response, daily steps, sedentary duration, commuting pattern
- Mood and stress: baseline mood, persistent low mood, stressors, coping strategies
- Past medical/surgical history and medication history
- Living environment: air quality, drinking-water source, cooking method

Once questioning ends, immediately move on to the recommendation output regardless of the final reply.

## Additional Notes
- Speak like a human physician and never reveal you are an AI assistant.
- Follow the prescribed number of roundsâ€”no more, no fewer.
- Combine initial symptoms with interview findings when reasoning.

The patientâ€™s disease-risk details are as follows:`;

const BASE_PROMPT_SUFFIX_WITH_COT = `
## Output Requirements

### Risk-level definitions
- High score (86-100)  = low disease risk
- Medium score (60-85) = medium disease risk
- Low score (0-60)     = high disease risk

### Recommendation Format (strict)
Every condition with a score under 86 (medium or high risk) **must** be included. Follow this template:

**Opening sentence:**
Your risk of ___ is ___ (High/Medium/Low).

**Recommendations (at least three):**
[1] Recommendation text; | Reasoning: tie the advice to specific user facts
[2] Recommendation text; | Reasoning: reference the userâ€™s metrics or habits
[3] Recommendation text; | Reasoning: explain why the recommendation is necessary

**Formatting guidelines:**
- Each line must start with `[number]` and end with a semicolon before the reasoning bar.
- Use `|` to separate the recommendation from its reasoning.
- Reasoning must reference concrete user responses or metrics.
- Add a line break after each recommendation.

**Example:**
If systemic lupus erythematosus is rated â€œLow scoreâ€?(meaning high risk):
Your risk of systemic lupus erythematosus is HIGH
[1] Limit sun exposure and avoid UV light; | Reasoning: the user frequently works outdoors and UV is a major trigger that worsens lesions
[2] Keep the immune system stable and avoid supplements that provoke immune overactivity; | Reasoning: lupus is autoimmune in origin, so immune balance lowers flare risk
[3] Avoid excessive fatigue and secure adequate rest; | Reasoning: heavy workloads reduce immune regulation and increase flare frequency

Apply this template to every medium/high risk diseaseâ€”no exceptions.

## Report Structure (Markdown)

Before the recommendations, output:
**-----Final Recommendation Feedback-----**

Then follow this structure:

## Personalized Health Management Report

### Overall Summary
(Provide a concise evaluation of the userâ€™s current health status.)

### Detailed Analysis

#### 1. Diet Habits Analysis
(Discuss dietary patterns, nutrient intake, and any imbalances.)

#### 2. Exercise Habits Analysis
(Cover exercise frequency, intensity, modality, and limitations.)

### Personalized Recommendations
(List diseases from highest to lowest risk using the strict format, covering diet, exercise, lifestyle, and mental health.)

### Summary and Encouragement
(Encourage adherence to healthy behaviors and recommend professional consultation if symptoms persist.)`;


let currentPrompt = BASE_PROMPT_PREFIX + '{{DISEASE_RISK}}' + BASE_PROMPT_SUFFIX_WITH_COT;


// åˆå§‹åŒ?Kimi å®¢æˆ·ç«?
const kimiClient = new OpenAI({
    apiKey: CONFIG.kimi.apiKey,
    baseURL: CONFIG.kimi.baseURL,
});

// MySQL è¿žæŽ¥æ±?
const pool = mysql.createPool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
});


const PYTHON = 'python3'; // æˆ–ç»å¯¹è·¯å¾„ï¼š'/www/.../venv/bin/python'
const SCRIPT = path.join(
  __dirname,
  'predict_cli.py'      // â†?ä½ çš„è„šæœ¬å®Œæ•´ä½ç½®
);
const PYTHON_ENV = path.join(__dirname, 'venv/bin/python3');
const LIFESTYLE_RISK_SCRIPT = path.join(__dirname, 'calculate_lifestyle_risk.py');

// å­˜å‚¨ç”¨æˆ·ä¸Šä¼ çš„æ–‡ä»¶è·¯å¾„ï¼ˆç”¨äºŽç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®—ï¼?
let currentUserFilePath = null;

async function ensurePdfDir() {
  try {
    await fs.mkdir(PDF_OUTPUT_DIR, { recursive: true });
  } catch (err) {
    console.error('åˆ›å»ºPDFç›®å½•å¤±è´¥:', err);
  }
}
ensurePdfDir();

// ============ 2. æ”¹è¿›çš„å¤„ç†å‡½æ•?============
async function processRAGFeedbackWithCOT(answer) {
  // æ£€æŸ¥æ˜¯å¦åŒ…å«RAGå…³é”®è¯?
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
  
  // è§£æžæ¯ä¸ªç–¾ç—…çš„å»ºè®®å’ŒæŽ¨ç†
  const resultsByKey = {};
  for (let i = 0; i < foundKeys.length; i++) {
    const { key, idx } = foundKeys[i];
    const start = idx + key.length + 2;
    const end = (i + 1 < foundKeys.length) ? foundKeys[i + 1].idx : answer.length;
    const segment = answer.slice(start, end);
    
    const items = [];
    // ä¿®æ”¹æ­£åˆ™è¡¨è¾¾å¼ä»¥æ•èŽ·å»ºè®®å’ŒæŽ¨ç†éƒ¨åˆ?
    const regex = /\[(\d+)\]([^[\]]*?)(?=[;\[]|$)/g;
    let m;
    while ((m = regex.exec(segment)) !== null) {
      const fullContent = m[2].trim();
      
      // åˆ†ç¦»å»ºè®®å’ŒæŽ¨ç†ï¼ˆä½¿ç”¨ç«–çº¿åˆ†éš”ï¼?
      const parts = fullContent.split('|');
      const suggestion = parts[0].replace(/[;ï¼›]$/, '').trim();
      const reasoning = parts[1] ? parts[1].replace(/^æŽ¨ç†[:ï¼š]/, '').trim() : '';
      
      items.push({ 
        num: m[1], 
        content: suggestion,
        reasoning: reasoning
      });
    }
    resultsByKey[key] = items;
  }
  
  // é‡å»ºæ–‡æœ¬ï¼ŒåŒ…å«æŽ¨ç?
  let rebuilt = prefix;
  
  for (const { key, dataDir, ext } of foundKeys) {
    rebuilt += key + ext + '\n';
    const items = resultsByKey[key] || [];
    
    for (const { num, content, reasoning } of items) {
      // æ·»åŠ å»ºè®®
      rebuilt += `[${num}] ${content};\n`;
      
      // èŽ·å–æ–‡çŒ®æ”¯æŒ
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
        pyOut = 'ï¼ˆæ£€ç´¢å‡ºé”™ï¼‰';
      }
      
      if (pyOut && pyOut !== 'ï¼ˆæ£€ç´¢å‡ºé”™ï¼‰') {
        rebuilt += `   æ–‡çŒ®æ”¯æŒ: ${pyOut}\n`;
      }
      
      // æ·»åŠ æŽ¨ç†è§£é‡Š
      if (reasoning) {
        rebuilt += `   æŽ¨ç†ä¾æ®: ${reasoning}\n`;
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
  // è‹¥å·²æ˜¯ç»å¯¹è·¯å¾„åˆ™ä¿æŒï¼Œä¸ç„¶æ‹¼æˆç»å¯?
  const filePath = path.isAbsolute(filePathRel)
                   ? filePathRel
                   : path.join(__dirname, filePathRel);

  return new Promise((resolve, reject) => {
    execFile(
      PYTHON,
      [SCRIPT, filePath],
      {
        cwd: path.join(__dirname, 'longevity_app')    // å…³é”®ï¼šåˆ‡åˆ?app æ ?
      },
      (error, stdout, stderr) => {
        if (stderr) console.error('[PY STDERR]', stderr);
        if (error)  return reject(error);

        try {
          const lastLine = stdout.trim().split('\n').pop();
          const data     = JSON.parse(lastLine);      // åªè§£æžæœ€åŽä¸€è¡?JSON
          resolve(data);
        } catch (e) {
          console.error('è§£æž Python è¾“å‡ºå¤±è´¥:', stdout);
          reject(e);
        }
      }
    );
  });
}


// æ–°å¢žï¼šè®¡ç®—ç”Ÿæ´»ä¹ æƒ¯é£Žé™©çš„å‡½æ•°ï¼ˆä¼ é€’æ–‡ä»¶è·¯å¾„ï¼Œç±»ä¼¼runPredictPythonï¼?
async function calculateLifestyleRisk(filePath) {
  return new Promise((resolve, reject) => {
    console.log('[Lifestyle Risk] è°ƒç”¨Pythonè„šæœ¬:', filePath);

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
          console.error('è®¡ç®—ç”Ÿæ´»ä¹ æƒ¯é£Žé™©å¤±è´¥:', error);
          return resolve(null); // å¤±è´¥æ—¶è¿”å›žnullï¼Œä¸å½±å“ä¸»æµç¨?
        }

        try {
          const lines = stdout.trim().split('\n');
          const lastLine = lines[lines.length - 1];
          const result = JSON.parse(lastLine);
          console.log('[Lifestyle Risk] è®¡ç®—æˆåŠŸï¼Œæ‰¾åˆ?, result.lifestyle_risks?.length || 0, 'ä¸ªtraits');
          resolve(result);
        } catch (e) {
          console.error('è§£æžç”Ÿæ´»ä¹ æƒ¯é£Žé™©ç»“æžœå¤±è´¥:', e);
          console.error('Pythonè¾“å‡º:', stdout);
          resolve(null);
        }
      }
    );
  });
}

// ä¸€æ¬¡æ€§ä¸ºå¤šä¸ªtraitsç”Ÿæˆå»ºè®®ï¼ˆæ‰¹é‡è°ƒç”¨ï¼Œæ›´å¿«ï¼?
async function generateAllLifestyleAdvice(traits) {
  try {
    // æž„å»ºåŒ…å«æ‰€æœ‰traitsçš„prompt
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

    console.log(`[Lifestyle Advice] æ‰¹é‡ç”Ÿæˆ5ä¸ªå»ºè®?..`);

    const response = await axios.post(
      `${CONFIG.kimi.baseURL}/chat/completions`,
      {
        model: 'moonshot-v1-8k',  // ä½¿ç”¨å¿«é€Ÿæ¨¡åž?
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
        timeout: 20000, // 20ç§’è¶…æ—¶ï¼ˆæ‰¹é‡å¤„ç†éœ€è¦æ›´å¤šæ—¶é—´ï¼‰
      }
    );

    const content = response.data.choices[0].message.content.trim();

    // å°è¯•è§£æžJSON
    let adviceMap = {};
    try {
      // æå–JSONéƒ¨åˆ†ï¼ˆå¯èƒ½åŒ…å«åœ¨```json```ä»£ç å—ä¸­ï¼?
      const jsonMatch = content.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        adviceMap = JSON.parse(jsonMatch[0]);
      }
    } catch (e) {
      console.error('[Lifestyle Advice] JSONè§£æžå¤±è´¥ï¼Œä½¿ç”¨fallbackå»ºè®®');
    }

    console.log(`[Lifestyle Advice] æ‰¹é‡ç”ŸæˆæˆåŠŸï¼Œè¿”å›?${Object.keys(adviceMap).length} ä¸ªå»ºè®®`);
    return adviceMap;

  } catch (error) {
    console.error(`[Lifestyle Advice] æ‰¹é‡ç”Ÿæˆå¤±è´¥:`, error.message);
    return {}; // è¿”å›žç©ºå¯¹è±¡ï¼Œä½¿ç”¨fallback
  }
}

// èŽ·å–å•ä¸ªtraitçš„å»ºè®®ï¼ˆä»Žæ‰¹é‡ç»“æžœä¸­æå–æˆ–ä½¿ç”¨fallbackï¼?
function getAdviceForTrait(traitName, riskLevel, adviceMap) {
  // å°è¯•ä»Žæ‰¹é‡ç”Ÿæˆçš„å»ºè®®ä¸­æŸ¥æ‰?
  const normalizedName = traitName.toLowerCase().replace(/[^a-z0-9]/g, '_');

  for (const key in adviceMap) {
    const normalizedKey = key.toLowerCase().replace(/[^a-z0-9]/g, '_');
    if (normalizedKey.includes(normalizedName) || normalizedName.includes(normalizedKey)) {
      return adviceMap[key];
    }
  }

  // Fallbackå»ºè®®
  if (riskLevel === 'high') {
    return 'This factor shows elevated levels. Consider consulting with a healthcare professional for personalized guidance.';
  } else if (riskLevel === 'medium') {
    return 'This factor requires attention. Monitor regularly and consider lifestyle modifications for optimal health.';
  } else {
    return 'This factor shows favorable levels. Continue maintaining your current healthy lifestyle habits.';
  }
}

// æ ¼å¼åŒ–ç”Ÿæ´»ä¹ æƒ¯é£Žé™©æŠ¥å‘Šï¼ˆè‹±æ–‡ç‰ˆï¼‰- åªæ˜¾ç¤ºå‰5ä¸ªpercentileæœ€é«˜çš„
async function formatLifestyleRiskReport(lifestyleData) {
  if (!lifestyleData || !lifestyleData.success || !lifestyleData.lifestyle_risks) {
    return '';
  }

  const risks = lifestyleData.lifestyle_risks;

  // æŒ‰ç…§percentileä»Žé«˜åˆ°ä½ŽæŽ’åºï¼Œå–å‰?ä¸?
  const topRisks = risks
    .sort((a, b) => b.percentile - a.percentile)
    .slice(0, 5);

  let report = '\n\n## Lifestyle Risk Assessment\n\n';
  report += 'Based on your protein expression profile, here are the top 5 lifestyle-related health factors that require attention:\n\n';

  // æ‰¹é‡ç”Ÿæˆæ‰€æœ?ä¸ªtraitsçš„å»ºè®®ï¼ˆä¸€æ¬¡APIè°ƒç”¨ï¼?
  const adviceMap = await generateAllLifestyleAdvice(topRisks);

  // ä¸ºæ¯ä¸ªtraitæ·»åŠ åˆ°æŠ¥å‘Šä¸­
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

// æ–°å¢žï¼šç”ŸæˆPDFçš„å‡½æ•?
// ä½¿ç”¨ç³»ç»ŸPythonè€Œä¸æ˜¯condaçŽ¯å¢ƒï¼Œé¿å…æƒé™é—®é¢?
const PYTHON_ENV2 = '/usr/bin/python3';  // ä½¿ç”¨å®Œæ•´è·¯å¾„ï¼Œé¿å…condaçŽ¯å¢ƒå¹²æ‰°
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

    // ä½¿ç”¨è‹±æ–‡ç‰ˆPDFç”Ÿæˆå™?
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
    console.error('ç”ŸæˆPDFå¤±è´¥:', error);
    return { success: false, error: error.message };
  }
}



// Middleware
app.use(express.static('.'));


function buildDiseaseRiskText(summary) {
  // æ³¨æ„ï¼šscoreToLevel è¿”å›žçš„æ˜¯ â€œåˆ†æ•°ï¼Œé£Žé™©â€ï¼ˆæ‹¬å·é‡Œæ˜¾ç¤ºçš„â€œä½Ž/ä¸?é«˜â€ä¸º**é£Žé™©ç­‰çº§**ï¼?
  return Object.entries(summary).map(([k, v]) => {
    const code = k.slice(-7);
    const name = DISEASE_DICT[code] || code;
    return `${name}[${scoreToLevel(v)}]`;
  }).join(' ');
}

// è°ƒç”¨ OpenAI API
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
        console.error('OpenAI API é”™è¯¯:', error.response.data || error.message);
        return 'OpenAI æš‚æ—¶æ— æ³•å›žç­”ã€?;
    }
}

// è°ƒç”¨ Kimi APIï¼ˆæ”¯æŒå¤šè½®å¯¹è¯ï¼‰
async function callKimi(question) {
    try {
        if (!kimiMessages) kimiMessages = [];
        
        const userMessage = {
            role: 'user',
            content: (currentPrompt || "") + question
        };
        
        kimiMessages.push({ role: 'user', content: question });
        
        const messages = [{ role: 'system', content: currentPrompt },      // â†?è¿™é‡Œæ˜¯çœŸæ­£çš„ã€Œæµç¨‹æç¤ºè¯ã€?
            ...kimiMessages.slice(-50)];                       // ä¿ç•™æœ€è¿?N æ¡å¯¹è¯?

        
        console.log("å‘é€ç»™Kimiçš„æ¶ˆæ?", messages);
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 600000);
        console.log('[KIMI â–º] messages:', messages);
        const completion = await kimiClient.chat.completions.create({
            model: CONFIG.kimi.model || "kimi-thinking-preview",
            messages: messages,
            temperature: 0.25,
            max_tokens: 8500
        }, {
            signal: controller.signal
        });
        console.log('[KIMI â—„] full completion:', completion);
        clearTimeout(timeoutId);
        
        if (!completion.choices[0].message.content) {
            throw new Error("Kimi è¿”å›žäº†ç©ºå“åº”");
        }
        
        const assistantMessage = completion.choices[0].message;
        kimiMessages.push(assistantMessage);
        
        if (kimiMessages.length > 50) {
            kimiMessages = kimiMessages.slice(-30);
        }
        
        return assistantMessage.content;
        
    } catch (error) {
        console.error('Kimi API é”™è¯¯è¯¦æƒ…:', error);
    
        const status = error.response?.status;
        const message = error.response?.data?.error?.message || error.message;
    
        if (!error.response) {
          return 'Kimi æš‚æ—¶æ— æ³•å›žç­”ï¼Œè¯·ç¨åŽå†è¯•';
        } else if (status === 429) {
          return 'è¯·æ±‚è¿‡äºŽé¢‘ç¹ï¼Œè¯·ç¨åŽå†è¯•';
        } else if (status >= 500) {
          return 'Kimi æœåŠ¡æš‚æ—¶ä¸å¯ç”?;
        } else {
          // å…¶å®ƒ 4xx é”™è¯¯
          return `Kimi é”™è¯¯ï¼?{message}`;
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
    
    console.log('æ”¶åˆ°èŠå¤©è¯·æ±‚:', { question, userId });
    
    // 1. èŽ·å–Kimiçš„è‹±æ–‡å›žç­?
    let rawAnswer = await (currentModel === 'openai'
      ? callOpenAI(question)
      : callKimi(question));
    
    console.log('=== AIåŽŸå§‹å›žå¤ ===');
    console.log(rawAnswer);
    console.log('=================\n');

    // 2. ç¿»è¯‘æˆä¸­æ–‡ï¼ˆç”¨äºŽå…³é”®è¯æ£€æµ‹å’ŒRAGï¼?
    console.log('å¼€å§‹ç¿»è¯‘æˆä¸­æ–‡...');
    const chineseAnswer = await translateToChinese(rawAnswer);
    
    console.log('=== ä¸­æ–‡ç¿»è¯‘ç»“æžœ ===');
    console.log(chineseAnswer);
    console.log('===================\n');

    // 3. ä½¿ç”¨ä¸­æ–‡ç‰ˆæœ¬è¿›è¡ŒRAGæ£€ç´?
    console.log('å¼€å§‹RAGå¤„ç†...');
    const ragResult = await processRAGFeedbackWithCOT(chineseAnswer);
    
    let processedChineseAnswer, isFinalReport;
    if (typeof ragResult === 'object' && ragResult !== null) {
      processedChineseAnswer = ragResult.processedAnswer || chineseAnswer;
      isFinalReport = ragResult.isFinalReport || false;
    } else {
      processedChineseAnswer = chineseAnswer;
      isFinalReport = false;
    }
    
    console.log('=== RAGå¤„ç†åŽçš„ä¸­æ–‡ ===');
    console.log(processedChineseAnswer);
    console.log('æ˜¯å¦ä¸ºæœ€ç»ˆæŠ¥å‘?', isFinalReport);
    console.log('======================\n');
    
    let pdfInfo = null;
    let finalEnglishReport = rawAnswer;

    // 4. å¦‚æžœæ˜¯æœ€ç»ˆæŠ¥å‘Šï¼Œæ·»åŠ å¥åº·åˆ†æ•°å¹¶ç¿»è¯‘å›žè‹±æ–‡
    if (isFinalReport) {
      console.log('æ£€æµ‹åˆ°æœ€ç»ˆæŠ¥å‘Šï¼Œå¼€å§‹æ·»åŠ å¥åº·åˆ†æ•?..');

      // Add health scores to the Chinese report first
      if (currentSummary) {
        const healthScoresSection = formatHealthScores(currentSummary);
        // Add scores before the final summary section
        const finalMarker = '### æ€»ç»“ä¸Žé¼“åŠ?;
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

      console.log('å¼€å§‹ç¿»è¯‘æˆè‹±æ–‡...');
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

      // è®¡ç®—å¹¶æ·»åŠ ç”Ÿæ´»ä¹ æƒ¯é£Žé™©è¯„ä¼?
      if (currentUserFilePath) {
        console.log('å¼€å§‹è®¡ç®—ç”Ÿæ´»ä¹ æƒ¯é£Žé™©ï¼Œæ–‡ä»¶è·¯å¾„:', currentUserFilePath);
        const lifestyleRiskData = await calculateLifestyleRisk(currentUserFilePath);

        if (lifestyleRiskData && lifestyleRiskData.success) {
          console.log('ç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®—æˆåŠŸï¼Œæ·»åŠ åˆ°æŠ¥å‘Šä¸?..');
          const lifestyleReport = await formatLifestyleRiskReport(lifestyleRiskData);

          // å°†ç”Ÿæ´»ä¹ æƒ¯é£Žé™©æŠ¥å‘Šæ·»åŠ åˆ°ç–¾ç—…é£Žé™©æŠ¥å‘Šä¹‹åŽï¼Œæ€»ç»“ä¹‹å‰
          const summaryMarker = '### Summary and Encouragement';
          if (finalEnglishReport.includes(summaryMarker)) {
            finalEnglishReport = finalEnglishReport.replace(
              summaryMarker,
              lifestyleReport + '\n' + summaryMarker
            );
          } else {
            // å¦‚æžœæ²¡æœ‰æ‰¾åˆ°æ€»ç»“æ ‡è®°ï¼Œå°±æ·»åŠ åˆ°æœ€å?
            finalEnglishReport += lifestyleReport;
          }
        } else {
          console.log('ç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®—å¤±è´¥æˆ–æ— æ•°æ®');
        }
      } else {
        console.log('è­¦å‘Šï¼šæ²¡æœ‰ç”¨æˆ·æ–‡ä»¶è·¯å¾„ï¼Œè·³è¿‡ç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®—');
      }

      console.log('=== æœ€ç»ˆè‹±æ–‡æŠ¥å‘?===');
      console.log(finalEnglishReport);
      console.log('===================\n');

      // ç”Ÿæˆè‹±æ–‡PDF
      pdfInfo = await generatePDF(finalEnglishReport, userId);
      
      if (!pdfInfo.success) {
        console.error('PDFç”Ÿæˆå¤±è´¥:', pdfInfo.error);
      } else {
        console.log('PDFç”ŸæˆæˆåŠŸ:', pdfInfo.pdfUrl);
      }
    }

    if (!finalEnglishReport || finalEnglishReport.trim() === '') {
      console.error('è­¦å‘Šï¼šæœ€ç»ˆè‹±æ–‡å›žç­”ä¸ºç©?);
      finalEnglishReport = 'Sorry, I am temporarily unable to generate a response. Please try again later.';
    }

    res.json({ 
      answer: finalEnglishReport,
      isFinalReport: isFinalReport,
      pdfInfo: pdfInfo
    });
    
  } catch (error) {
    console.error('èŠå¤©APIé”™è¯¯:', error);
    res.status(500).json({ 
      error: 'Server error',
      message: error.message 
    });
  }
});

// æ–°å¢žï¼šPDFä¸‹è½½ç«¯ç‚¹
app.get('/api/download-pdf/:filename', async (req, res) => {
  try {
    const { filename } = req.params;
    
    // å®‰å…¨æ€§æ£€æŸ¥ï¼šé˜²æ­¢è·¯å¾„éåŽ†
    if (filename.includes('..') || filename.includes('/')) {
      return res.status(400).json({ error: 'æ— æ•ˆçš„æ–‡ä»¶å' });
    }
    
    const filePath = path.join(PDF_OUTPUT_DIR, filename);
    
    // æ£€æŸ¥æ–‡ä»¶æ˜¯å¦å­˜åœ?
    try {
      await fs.access(filePath);
    } catch {
      return res.status(404).json({ error: 'æ–‡ä»¶ä¸å­˜åœ? });
    }
    
    // è®¾ç½®å“åº”å¤?
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
    
    // å‘é€æ–‡ä»?
    res.sendFile(filePath);
    
  } catch (error) {
    console.error('ä¸‹è½½PDFå¤±è´¥:', error);
    res.status(500).json({ error: 'ä¸‹è½½å¤±è´¥' });
  }
});

// æ–°å¢žï¼šèŽ·å–ç”¨æˆ·çš„åŽ†å²PDFæŠ¥å‘Šåˆ—è¡¨
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
    console.error('èŽ·å–PDFåŽ†å²å¤±è´¥:', error);
    res.status(500).json({ error: 'èŽ·å–åŽ†å²å¤±è´¥' });
  }
});

// æ·»åŠ é™æ€æ–‡ä»¶æœåŠ¡ï¼ˆå¦‚æžœéœ€è¦ç›´æŽ¥è®¿é—®PDFï¼?
app.use('/pdfs', express.static(PDF_OUTPUT_DIR));


// API endpoint to update the prompt
app.post('/api/update-prompt', (req, res) => {
    const { prompt } = req.body;
    if (prompt) {
        currentPrompt = prompt;
        res.json({ success: true, message: 'æç¤ºè¯å·²æ›´æ–°' });
    } else {
        res.status(400).json({ error: 'æç¤ºè¯ä¸èƒ½ä¸ºç©? });
    }
});

// API endpoint to switch models
app.post('/api/switch-model', (req, res) => {
    const { model } = req.body;
    if (['openai', 'kimi'].includes(model)) {
        currentModel = model;
        res.json({ success: true, message: `å·²åˆ‡æ¢åˆ° ${model} æ¨¡åž‹` });
    } else {
        res.status(400).json({ error: 'æ— æ•ˆçš„æ¨¡åž‹åç§? });
    }
});

// æ–°å¢žï¼šæ–°å»ºå¯¹è¯APIç«¯ç‚¹
app.post('/api/new-chat', (req, res) => {
    try {
        // æ¸…ç©ºå¯¹è¯åŽ†å²
        kimiMessages = [];
        console.log('å¯¹è¯åŽ†å²å·²é‡ç½?);
        res.json({ success: true, message: 'å·²å¼€å§‹æ–°çš„å¯¹è¯? });
    } catch (error) {
        res.status(500).json({ 
            error: 'åˆ›å»ºæ–°ä¼šè¯å¤±è´?,
            details: error.message
        });
    }
});

app.post('/api/register', async (req, res) => {
  const { phone, password, age, gender } = req.body;
  if (!/^1\d{10}$/.test(phone) || !password) {
    return res.status(400).json({ error: 'æ‰‹æœºå·æˆ–å¯†ç æ ¼å¼ä¸æ­£ç¡?!!' });
  }

  // éªŒè¯å¹´é¾„å’Œæ€§åˆ«
  if (!age || age < 1 || age > 150) {
    return res.status(400).json({ error: 'è¯·è¾“å…¥æœ‰æ•ˆçš„å¹´é¾„ (1-150)' });
  }
  if (!gender || gender.trim() === '') {
    return res.status(400).json({ error: 'æ€§åˆ«ä¸èƒ½ä¸ºç©º' });
  }

  try {
    const [rows] = await pool.query('SELECT id FROM users WHERE phone=?', [phone]);
    if (rows.length) return res.status(409).json({ error: 'è´¦å·å·²å­˜åœ? });

    const hash = await bcrypt.hash(password, 10);
    await pool.query(
      'INSERT INTO users (phone, password, age, gender) VALUES (?, ?, ?, ?)',
      [phone, hash, age, gender]
    );
    res.json({ success: true, message: 'æ³¨å†ŒæˆåŠŸ' });
  } catch (e) {
    console.error('æ³¨å†Œé”™è¯¯:', e);
    res.status(500).json({ error: 'æ•°æ®åº“é”™è¯? });
  }
});

app.post('/api/login', async (req, res) => {
  const { phone, password } = req.body;
  try {
    const [rows] = await pool.query('SELECT id, password FROM users WHERE phone=?', [phone]);
    if (!rows.length) return res.status(401).json({ error: 'è´¦å·ä¸å­˜åœ? });

    const match = await bcrypt.compare(password, rows[0].password);
    if (!match) return res.status(401).json({ error: 'å¯†ç é”™è¯¯' });

    res.json({ success: true, userId: rows[0].id });
  } catch (e) {
    res.status(500).json({ error: 'æ•°æ®åº“é”™è¯? });
  }
});

// æ–°å¢žï¼šä½¿ç”¨ç¤ºä¾‹æ–‡ä»¶çš„APIç«¯ç‚¹
app.post('/api/use-sample-file', async (req, res) => {
  const { userId } = req.body;

  // æœåŠ¡å™¨ä¸Šçš„ç¤ºä¾‹æ–‡ä»¶è·¯å¾?
  const SAMPLE_FILE_PATH = 'date_test_7_11.xlsx';

  const conn = await pool.getConnection();
  try {
    // æ£€æŸ¥ç¤ºä¾‹æ–‡ä»¶æ˜¯å¦å­˜åœ?
    try {
      await fs.access(SAMPLE_FILE_PATH);
    } catch {
      return res.status(404).json({ error: 'ç¤ºä¾‹æ–‡ä»¶ä¸å­˜åœ? });
    }

    // åˆ›å»ºä¸€ä¸ªä¸´æ—¶å‰¯æœ¬ç”¨äºŽå¤„ç†ï¼ˆé¿å…ä¿®æ”¹åŽŸå§‹ç¤ºä¾‹æ–‡ä»¶ï¼?
    const tempFileName = `sample_${Date.now()}_date_test_7_11.xlsx`;
    const tempFilePath = path.join('uploads/', tempFileName);
    await fs.copyFile(SAMPLE_FILE_PATH, tempFilePath);

    // è®°å½•åˆ°æ•°æ®åº“
    const [result] = await conn.query(
      'INSERT INTO user_files (user_id, file_path) VALUES (?, ?)',
      [userId, tempFilePath]
    );
    const srcFileId = result.insertId;

    // CRITICAL: åœ¨ç–¾ç—…é¢„æµ‹ä¹‹å‰ï¼Œå…ˆå¤åˆ¶åŽŸå§‹æ–‡ä»¶ç”¨äºŽç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®?
    const originalFilePath = tempFilePath.replace('.xlsx', '_original.xlsx');
    await fs.copyFile(tempFilePath, originalFilePath);
    console.log('å¤‡ä»½åŽŸå§‹æ–‡ä»¶:', originalFilePath);

    // ä½¿ç”¨ä¸Šä¼ çš„æ–‡ä»¶è¿›è¡Œç–¾ç—…é¢„æµ‹ï¼ˆè¿™ä¸ªæ–‡ä»¶å¯èƒ½ä¼šè¢«ä¿®æ”¹ï¼?
    const { resultPath, summary } = await runPredictPython(tempFilePath);

    // ä¿å­˜å¤‡ä»½çš„åŽŸå§‹æ–‡ä»¶è·¯å¾„ï¼ˆç”¨äºŽç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®—ï¼?
    currentUserFilePath = originalFilePath;
    console.log('ä¿å­˜åŽŸå§‹æ–‡ä»¶è·¯å¾„ç”¨äºŽç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®—:', currentUserFilePath);

    // Store summary globally
    currentSummary = summary;
    const mustCover = getTargetDiseases(summary);
    const mustCoverList = mustCover.map((n,i)=>`${i+1}. ${n}`).join('\n');
    const diseaseRiskText = buildDiseaseRiskText(summary);
    const HARD_REQUIRE =
    `\n\n### å¿…é¡»é€ä¸€è¦†ç›–çš„ç–¾ç—…æ¸…å•ï¼ˆè¯„åˆ†<86ï¼?
    ${mustCoverList}

    - ä¸Šè¿°æ¯ä¸ªç–¾ç—… **éƒ½å¿…é¡?* è¾“å‡ºä¸€æ®µï¼š
      - æ ‡é¢˜è¡Œï¼šæ‚¨æ‚£___çš„é£Žé™©è¾ƒ___
      - è‡³å°‘3æ?[ç¼–å·] å»ºè®®ï¼Œæ¯æ¡éƒ½å?"æ–‡çŒ®æ”¯æŒ/æŽ¨ç†ä¾æ®"ï¼ˆè‹¥æ— æ–‡çŒ®ï¼Œå¯ç©ºå ä½ï¼?
    - è‹¥ä»»ä½•ä¸€ä¸ªç–¾ç—…æœªè¦†ç›–ï¼Œå›žç­?**æ— æ•ˆ**ï¼Œè¯·ç»§ç»­ç”Ÿæˆï¼Œç›´è‡³å…¨éƒ¨ç–¾ç—…è¦†ç›–å®Œæˆã€‚`;

    currentPrompt = BASE_PROMPT_PREFIX + buildDiseaseRiskText(summary) + BASE_PROMPT_SUFFIX_WITH_COT + HARD_REQUIRE;
    console.log('[DEBUG] ä½¿ç”¨ç¤ºä¾‹æ–‡ä»¶ï¼Œæ›´æ–°æç¤ºè¯');

    await conn.query(
      `INSERT INTO prediction_results
       (user_id, src_file_path, result_file_path, summary_json)
       VALUES (?,?,?,?)`,
      [userId, tempFilePath, resultPath, JSON.stringify(summary)]
    );

    res.json({
      success: true,
      message: 'ç¤ºä¾‹æ–‡ä»¶åŠ è½½æˆåŠŸ',
      srcFileId,
      resultPath,
      summary
    });
  } catch (e) {
    console.error('ä½¿ç”¨ç¤ºä¾‹æ–‡ä»¶é”™è¯¯:', e);
    res.status(500).json({ error: 'æœåŠ¡å™¨å¤„ç†å¤±è´? });
  } finally {
    conn.release();
  }
});

app.post('/api/upload', upload.single('file'), async (req, res) => {
  const { userId } = req.body;
  if (!req.file) return res.status(400).json({ error: 'æœªæ£€æµ‹åˆ°æ–‡ä»¶' });

  const conn = await pool.getConnection();
  try {
    const [result] = await conn.query(
      'INSERT INTO user_files (user_id, file_path) VALUES (?, ?)',
      [userId, req.file.path]
    );
    const srcFileId = result.insertId;

    // CRITICAL: åœ¨ç–¾ç—…é¢„æµ‹ä¹‹å‰ï¼Œå…ˆå¤åˆ¶åŽŸå§‹æ–‡ä»¶ç”¨äºŽç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®?
    // å› ä¸ºç–¾ç—…é¢„æµ‹è„šæœ¬ä¼šä¿®æ”¹åŽŸå§‹æ–‡ä»¶ï¼Œå¯¼è‡´ç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®—è¯»å–åˆ°é”™è¯¯çš„æ•°æ®
    const originalFilePath = req.file.path.replace('.xlsx', '_original.xlsx');
    await fs.copyFile(req.file.path, originalFilePath);
    console.log('å¤‡ä»½åŽŸå§‹æ–‡ä»¶:', originalFilePath);

    // ä½¿ç”¨ä¸Šä¼ çš„æ–‡ä»¶è¿›è¡Œç–¾ç—…é¢„æµ‹ï¼ˆè¿™ä¸ªæ–‡ä»¶å¯èƒ½ä¼šè¢«ä¿®æ”¹ï¼?
    const { resultPath, summary } = await runPredictPython(req.file.path);

    // ä¿å­˜å¤‡ä»½çš„åŽŸå§‹æ–‡ä»¶è·¯å¾„ï¼ˆç”¨äºŽç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®—ï¼?
    // è¿™ä¸ªæ–‡ä»¶ä¿æŒ825åˆ—ä¸å˜ï¼Œä¸ä¼šè¢«ç–¾ç—…é¢„æµ‹è„šæœ¬ä¿®æ”?
    currentUserFilePath = originalFilePath;
    console.log('ä¿å­˜åŽŸå§‹æ–‡ä»¶è·¯å¾„ç”¨äºŽç”Ÿæ´»ä¹ æƒ¯é£Žé™©è®¡ç®—:', currentUserFilePath);
    
    // Store summary globally
    currentSummary = summary;
    const mustCover = getTargetDiseases(summary);
    const mustCoverList = mustCover.map((n,i)=>`${i+1}. ${n}`).join('\n');
    const diseaseRiskText = buildDiseaseRiskText(summary);
    const HARD_REQUIRE =
    `\n\n### å¿…é¡»é€ä¸€è¦†ç›–çš„ç–¾ç—…æ¸…å•ï¼ˆè¯„åˆ†<86ï¼?
    ${mustCoverList}
    
    - ä¸Šè¿°æ¯ä¸ªç–¾ç—… **éƒ½å¿…é¡?* è¾“å‡ºä¸€æ®µï¼š
      - æ ‡é¢˜è¡Œï¼šæ‚¨æ‚£___çš„é£Žé™©è¾ƒ___
      - è‡³å°‘3æ?[ç¼–å·] å»ºè®®ï¼Œæ¯æ¡éƒ½å?â€œæ–‡çŒ®æ”¯æŒ?æŽ¨ç†ä¾æ®â€ï¼ˆè‹¥æ— æ–‡çŒ®ï¼Œå¯ç©ºå ä½ï¼‰
    - è‹¥ä»»ä½•ä¸€ä¸ªç–¾ç—…æœªè¦†ç›–ï¼Œå›žç­?**æ— æ•ˆ**ï¼Œè¯·ç»§ç»­ç”Ÿæˆï¼Œç›´è‡³å…¨éƒ¨ç–¾ç—…è¦†ç›–å®Œæˆã€‚`;
    
    currentPrompt = BASE_PROMPT_PREFIX + buildDiseaseRiskText(summary) + BASE_PROMPT_SUFFIX_WITH_COT + HARD_REQUIRE;
    console.log('[DEBUG] æ›´æ–°æç¤ºè¯ï¼Œç–¾ç—…é£Žé™©æ–‡æœ¬:', diseaseRiskText);
    
    await conn.query(
      `INSERT INTO prediction_results
       (user_id, src_file_path, result_file_path, summary_json)
       VALUES (?,?,?,?)`,
      [userId, req.file.path, resultPath, JSON.stringify(summary)]
    );

    res.json({
      success: true,
      message: 'æ–‡ä»¶ä¸Šä¼ æˆåŠŸ',
      srcFileId,
      resultPath,
      summary
    });
  } catch (e) {
    console.error('ä¸Šä¼ å¤„ç†é”™è¯¯:', e);
    res.status(500).json({ error: 'æœåŠ¡å™¨å¤„ç†å¤±è´? });
  } finally {
    conn.release();
  }
});


// å°†åˆ†æ•°æ˜ å°„ä¸ºâ€œé£Žé™©ç­‰çº§â€ï¼ˆæ³¨æ„ï¼šåˆ†é«˜â†’é£Žé™©ä½Žï¼‰
function scoreToRisk(score) {
  const s = Number
(score);
  if (s <= 60) return 'é«?;     // é£Žé™©é«?
  if (s <= 85) return 'ä¸?;     // é£Žé™©ä¸?
  return 'ä½?;                  // é£Žé™©ä½Žï¼ˆ86+ï¼?
}

// æŒ‰ä½ çš„éœ€æ±‚ï¼šè¿”å›ž â€œåˆ†æ•°ï¼Œé£Žé™©â€?
function scoreToLevel(score) {
  const s = Math.round(Number
(score));
  const risk = scoreToRisk
(s);
  return `${s}ï¼?{risk}`;       // ä¾‹å¦‚ "59ï¼Œä½Ž"ï¼ˆè¡¨ç¤ºåˆ†æ•?9ï¼Œå¯¹åº”é£Žé™©â€œä½Ž/ä¸?é«˜â€ï¼‰
}


// ä¸è¦ç”?'.'ï¼Œæ˜¾å¼æŒ‡å®šé™æ€ç›®å½•ï¼ˆæŒ‰ä½ çš„é¡¹ç›®ç»“æž„æ”¹ï¼?
app.use(express.static(path.join(__dirname))); // æˆ?publicã€dist ç­?

const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '0.0.0.0';

app.get('/healthz', (req, res) => res.send('ok'));

app.listen(PORT, HOST, () => {
  console.log(`Server listening on http://${HOST}:${PORT}`);
});
