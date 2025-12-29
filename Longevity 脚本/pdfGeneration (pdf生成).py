#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
from datetime import datetime
try:
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(r"C:\msys64\ucrt64\bin")
except Exception:
    pass
from weasyprint import HTML, CSS

# Updated HTML Template with FIXED layout
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>
        @page {
            size: A4;
            margin: 2cm;
            @top-center {
                content: "Personal Health Management Report";
                font-size: 10pt;
                color: #666;
            }
            @bottom-center {
                content: "Page " counter(page);
                font-size: 10pt;
                color: #666;
            }
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Arial', 'Helvetica', sans-serif;
            line-height: 1.6;
            color: #333;
            background: white;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 28px;
            margin-bottom: 10px;
            font-weight: 600;
        }
        
        .header .subtitle {
            font-size: 14px;
            opacity: 0.9;
        }
        
        .header .date {
            font-size: 12px;
            margin-top: 10px;
            opacity: 0.8;
        }
        
        .health-scores-section {
            background: linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%);
            border: 2px solid #667eea;
            border-radius: 10px;
            padding: 25px;
            margin-bottom: 30px;
            page-break-inside: avoid;
        }
        
        .health-scores-section h2 {
            color: #667eea;
            font-size: 22px;
            margin-bottom: 20px;
            text-align: center;
            font-weight: 600;
        }
        
        .scores-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        .scores-table tr {
            border-bottom: 1px solid #e0e0e0;
        }
        
        .scores-table td {
            padding: 10px;
            vertical-align: middle;
        }
        
        .scores-table td:first-child {
            font-size: 13px;
            color: #495057;
            font-weight: 500;
            width: 70%;
        }
        
        .scores-table td:last-child {
            text-align: right;
            width: 30%;
        }
        
        .score-value {
            display: inline-block;
            font-size: 16px;
            font-weight: bold;
            padding: 4px 10px;
            border-radius: 5px;
            min-width: 70px;
            text-align: center;
        }
        
        .score-high {
            background: #e8f5e9;
            color: #2e7d32;
        }
        
        .score-medium {
            background: #fff3e0;
            color: #ef6c00;
        }
        
        .score-low {
            background: #ffebee;
            color: #c62828;
        }
        
        .summary-card {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 20px;
            margin-bottom: 25px;
            border-radius: 5px;
        }
        
        .summary-card h2 {
            color: #667eea;
            font-size: 18px;
            margin-bottom: 10px;
        }
        
        .risk-section {
            margin-bottom: 30px;
        }
        
        .risk-card {
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            page-break-inside: avoid;
        }
        
        .risk-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #f1f3f5;
        }
        
        .disease-name {
            font-size: 18px;
            font-weight: 600;
            color: #495057;
        }
        
        .risk-level {
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 500;
        }
        
        .risk-high {
            background: #ffebee;
            color: #c62828;
        }
        
        .risk-medium {
            background: #fff3e0;
            color: #ef6c00;
        }
        
        .risk-low {
            background: #e8f5e9;
            color: #2e7d32;
        }
        
        .suggestions {
            margin-top: 15px;
        }
        
        .suggestion-item {
            background: #f8f9fa;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 5px;
            border-left: 3px solid #667eea;
        }
        
        .suggestion-number {
            display: inline-block;
            background: #667eea;
            color: white;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            text-align: center;
            line-height: 24px;
            font-size: 12px;
            margin-right: 10px;
        }
        
        .suggestion-content {
            margin-bottom: 8px;
            font-size: 14px;
        }
        
        .evidence {
            font-size: 12px;
            color: #6c757d;
            padding-left: 34px;
            margin-top: 5px;
        }
        
        .evidence-label {
            font-weight: 600;
            color: #495057;
        }
        
        .lifestyle-section {
            background: #f0f7ff;
            border: 1px solid #90caf9;
            border-radius: 8px;
            padding: 25px;
            margin: 30px 0;
            page-break-inside: avoid;
        }
        
        .lifestyle-section h2 {
            color: #1976d2;
            font-size: 20px;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
        }
        
        .lifestyle-section h2 .icon {
            margin-right: 10px;
            font-size: 24px;
        }
        
        .lifestyle-content {
            line-height: 1.8;
            color: #424242;
        }
        
        .lifestyle-content ul {
            list-style-type: none;
            padding-left: 0;
        }
        
        .lifestyle-content li {
            background: white;
            padding: 10px 15px;
            margin-bottom: 10px;
            border-radius: 5px;
            border-left: 3px solid #1976d2;
        }
        
        .lifestyle-content li strong {
            color: #1565c0;
        }
        
        .lifestyle-summary {
            margin-top: 15px;
            padding: 15px;
            background: #e3f2fd;
            border-radius: 5px;
            font-weight: 500;
        }
        
        .overall-section {
            background: #f0f7ff;
            border: 1px solid #90caf9;
            border-radius: 8px;
            padding: 25px;
            margin-top: 30px;
        }
        
        .overall-section h2 {
            color: #1976d2;
            font-size: 20px;
            margin-bottom: 15px;
        }
        
        .overall-content {
            line-height: 1.8;
            color: #424242;
        }

        .lifestyle-risk-section {
            background: #f0f9ff;
            border: 2px solid #0284c7;
            border-radius: 10px;
            padding: 25px;
            margin: 30px 0;
            page-break-inside: avoid;
        }

        .lifestyle-risk-section h2 {
            color: #0369a1;
            font-size: 22px;
            margin-bottom: 20px;
            text-align: center;
        }

        .lifestyle-risk-section h3 {
            color: #0284c7;
            font-size: 18px;
            margin-top: 20px;
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 2px solid #bae6fd;
        }

        .lifestyle-risk-item {
            background: white;
            border: 1px solid #e0f2fe;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 12px;
        }

        .lifestyle-risk-item h4 {
            color: #075985;
            font-size: 15px;
            margin-bottom: 8px;
        }

        .lifestyle-risk-item .chinese-name {
            color: #64748b;
            font-size: 13px;
            font-weight: normal;
        }

        .lifestyle-risk-item .risk-info {
            font-size: 13px;
            color: #475569;
            line-height: 1.6;
            margin: 5px 0;
        }

        .lifestyle-risk-item .risk-description {
            color: #64748b;
            font-size: 13px;
            font-style: italic;
            margin-top: 8px;
        }

        .positive-factors-list {
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 6px;
            padding: 15px;
            margin-top: 10px;
        }

        .positive-factors-list ul {
            list-style-type: none;
            padding-left: 0;
            margin: 10px 0;
        }

        .positive-factors-list li {
            padding: 5px 0;
            color: #166534;
            font-size: 13px;
        }

        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #e9ecef;
            text-align: center;
            font-size: 12px;
            color: #6c757d;
        }
        
        .footer .disclaimer {
            margin-top: 10px;
            font-style: italic;
        }
        
        @media print {
            .risk-card, .lifestyle-section, .health-scores-section {
                page-break-inside: avoid;
            }
            
            .header {
                background: #667eea !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Personal Health Management Report</h1>
        <div class="subtitle">Personalized recommendations based on your health data</div>
        <div class="date">{{report_date}}</div>
    </div>
    
    {{health_scores}}
    
    <div class="summary-card">
        <h2>📋 Report Summary</h2>
        <p>Based on the analysis of your health data, we have identified health risks that require attention and provided corresponding preventive recommendations. Please read the following content carefully and gradually implement these suggestions in your daily life.</p>
    </div>
    
    {{diet_analysis}}
    
    {{exercise_analysis}}
    
    <div class="risk-section">
        {{risk_cards}}
    </div>
    
    {{overall_suggestions}}

    {{lifestyle_risk}}

    <div class="footer">
        <p>Report generated: {{generation_time}}</p>
        <p class="disclaimer">
            Disclaimer: This report is for reference only and cannot replace professional medical advice. If you have health concerns, please consult a healthcare professional.
        </p>
    </div>
</body>
</html>
"""

def extract_health_scores(content):
    """Extract health scores from the report"""
    scores = []
    
    # Look for the health scores section
    score_markers = ['### Your health score:', '### Health Score:', 'Your health score:']
    
    for marker in score_markers:
        if marker in content:
            start_idx = content.index(marker)
            # Find the end of scores section - be more careful
            end_idx = len(content)
            
            # Look for next section markers
            next_markers = ['\n### ', '\n## ', '-----', 'Summary and Encouragement']
            for next_marker in next_markers:
                if next_marker in content[start_idx:]:
                    temp_idx = content[start_idx:].index(next_marker)
                    end_idx = min(end_idx, start_idx + temp_idx)
            
            scores_content = content[start_idx:end_idx].strip()
            lines = scores_content.split('\n')
            
            for line in lines[1:]:  # Skip header
                line = line.strip()
                if ':' in line and '/' in line:
                    parts = line.split(':')
                    if len(parts) == 2:
                        disease = parts[0].strip()
                        score_part = parts[1].strip()
                        if '/' in score_part:
                            score_value = score_part.split('/')[0].strip()
                            try:
                                score_num = int(score_value)
                                scores.append({
                                    'disease': disease,
                                    'score': score_num
                                })
                            except ValueError:
                                continue
            break
    
    return scores

def format_health_scores_html(scores):
    """Format health scores into HTML table format"""
    if not scores:
        return ''
    
    # Build table rows
    table_rows = ''
    for score_data in scores:
        original_score = score_data['score']
        disease = score_data['disease']

        # Convert score: risk_score = (100 - original_score) / 60
        # Score range is [40, 100], mapped to risk range [1.0, 0.0]
        # Higher original score (86+) → Lower risk score (0.23) → Green (low risk)
        # Lower original score (40-60) → Higher risk score (0.67-1.00) → Red (high risk)
        risk_score = (100 - original_score) / 60

        # Determine score level based on converted risk score
        # Lower risk score = lower risk (green)
        # Higher risk score = higher risk (red)
        if risk_score <= 0.25:  # original >= 85
            score_class = 'score-high'  # Green (low risk)
        elif risk_score <= 0.67:  # original >= 60
            score_class = 'score-medium'  # Orange (medium risk)
        else:  # risk_score > 0.67, original < 60
            score_class = 'score-low'  # Red (high risk)

        table_rows += f'''
        <tr>
            <td>{disease}</td>
            <td><span class="score-value {score_class}">{risk_score:.2f}</span></td>
        </tr>
        '''

    return f'''
    <div class="health-scores-section">
        <h2>🎯 Your Health Risk Assessment Scores</h2>
        <table class="scores-table">
            {table_rows}
        </table>
        <p style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
            Risk Score Range: 0.00-0.25 (Low Risk), 0.26-0.67 (Medium Risk), 0.68-1.00 (High Risk) | Lower scores indicate lower risk
        </p>
    </div>
    '''

def parse_disease_risks(content):
    """Parse ALL disease risks with robust section bounds and Literature Support fallback"""
    risks = []
    seen_diseases = set()

    # Precompute the position of the health score header (to hard-stop last disease)
    score_markers = [r'### Your health score:', r'### Health Score:', r'Your health score:']
    score_pos = None
    for m in score_markers:
        idx = content.find(m)
        if idx != -1:
            score_pos = idx if score_pos is None else min(score_pos, idx)

    # 1) Find all disease risk statements
    risk_patterns = [
        r'Your risk of ([^.]+?) is (HIGH|MEDIUM|LOW)',
        r'Your risk for ([^.]+?) is (HIGH|MEDIUM|LOW)',
    ]
    all_matches = []
    for pattern in risk_patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            disease_name = match.group(1).strip()
            risk_level = match.group(2).upper()
            position = match.start()
            if disease_name.lower() not in seen_diseases:
                all_matches.append({
                    'disease': disease_name,
                    'level': risk_level,
                    'position': position
                })
                seen_diseases.add(disease_name.lower())

    # Sort by appearance
    all_matches.sort(key=lambda x: x['position'])

    # 2) For each disease block, slice safely
    for i, match_data in enumerate(all_matches):
        disease = match_data['disease']
        level = match_data['level']
        start_pos = match_data['position']

        # end at next disease or health-score header or content end — whichever comes first
        next_disease_pos = all_matches[i + 1]['position'] if (i + 1) < len(all_matches) else len(content)
        candidate_end = next_disease_pos
        if score_pos is not None and score_pos > start_pos:
            candidate_end = min(candidate_end, score_pos)
        end_pos = min(candidate_end, len(content))

        section = content[start_pos:end_pos]

        # 3) Extract numbered suggestions robustly.
        #    Stop each suggestion at next [n], next disease header, or score header.
        suggestion_pattern = r'\[(\d+)\]\s*([^\[]+?)(?=\[\d+\]|\n?Your risk|\n?### Your health score:|$)'
        suggestions = []
        for sug_match in re.finditer(suggestion_pattern, section, re.DOTALL | re.IGNORECASE):
            num = sug_match.group(1)
            full_text = sug_match.group(2).strip()

            # Normalize whitespace for easier regex parsing
            block = re.sub(r'[ \t]+', ' ', full_text)
            block = re.sub(r'\r', '', block)

            # --- Extract parts ---
            # First line (up to first semicolon) is the recommendation line
            # (if the semicolon is missing, we still try to use the first non-empty line)
            suggestion_text = ''
            # Capture everything until the first semicolon as the core recommendation text
            m_sugg = re.search(r'^(.*?);', block)
            if m_sugg:
                suggestion_text = m_sugg.group(1).strip()
            else:
                # Fallback: take the first line (and strip trailing label tokens if any)
                first_line = block.split('\n', 1)[0].strip()
                # Avoid leading labels
                if not first_line.lower().startswith('literature support:') and not first_line.lower().startswith('reasoning:'):
                    suggestion_text = first_line.strip()

            # Primary: explicit "Literature Support:" → capture up to "Reasoning:"
            evidence = ''
            m_evid = re.search(r'Literature Support:\s*(.*?)\s*Reasoning:', block, re.DOTALL | re.IGNORECASE)
            if m_evid:
                evidence = m_evid.group(1).strip()
            else:
                # Fallback (double insurance): grab text AFTER the semicolon of the suggestion
                # and BEFORE "Reasoning:" even if the explicit label is missing.
                m_evid_fallback = re.search(r';\s*(.*?)\s*Reasoning:', block, re.DOTALL | re.IGNORECASE)
                if m_evid_fallback:
                    evidence = m_evid_fallback.group(1).strip()
                    # If the fallback caught a duplicated keyword, trim it
                    evidence = re.sub(r'^\s*Literature Support:\s*', '', evidence, flags=re.IGNORECASE).strip()

            # Reasoning: from "Reasoning:" to the end (but NOT beyond any stray scores header)
            reasoning = ''
            m_reason = re.search(r'Reasoning:\s*(.*)$', block, re.DOTALL | re.IGNORECASE)
            if m_reason:
                reasoning = m_reason.group(1).strip()
                # Defensive cut if someone forgot to clip at scores header inside the block
                reasoning = reasoning.split('### Your health score:')[0].strip()

            if suggestion_text:
                suggestions.append({
                    'number': num,
                    'content': suggestion_text,
                    'evidence': evidence,
                    'reasoning': reasoning
                })

        if suggestions:
            risks.append({
                'disease': disease,
                'level': level,
                'suggestions': suggestions
            })

    return risks

def extract_diet_analysis(content):
    """Extract dietary habits analysis section"""
    diet_markers = ['#### 1. Dietary Habits Analysis', '#### 1. Diet Analysis', 'Dietary Habits Analysis']
    
    for marker in diet_markers:
        if marker in content:
            start_idx = content.index(marker)
            
            # Find end markers
            end_markers = ['#### 2. Exercise', '### ', 'Your risk', '-----']
            end_idx = len(content)
            
            for end_marker in end_markers:
                if end_marker in content[start_idx + len(marker):]:
                    temp_idx = content.index(end_marker, start_idx + len(marker))
                    end_idx = min(end_idx, temp_idx)
            
            diet_content = content[start_idx:end_idx].strip()
            # Remove the marker line
            lines = diet_content.split('\n')
            diet_content = '\n'.join(lines[1:])
            return diet_content.strip()
    
    return ''

def extract_exercise_analysis(content):
    """Extract exercise habits analysis section"""
    exercise_markers = ['#### 2. Exercise Habits Analysis', '#### 2. Exercise Analysis']
    
    for marker in exercise_markers:
        if marker in content:
            start_idx = content.index(marker)
            
            # Find end markers
            end_markers = ['### ', 'Your risk', '-----', 'Your health score:']
            end_idx = len(content)
            
            for end_marker in end_markers:
                if end_marker in content[start_idx + len(marker):]:
                    temp_idx = content.index(end_marker, start_idx + len(marker))
                    end_idx = min(end_idx, temp_idx)
            
            exercise_content = content[start_idx:end_idx].strip()
            # Remove the marker line
            lines = exercise_content.split('\n')
            exercise_content = '\n'.join(lines[1:])
            return exercise_content.strip()
    
    return ''

def format_lifestyle_content(content, title, icon):
    """Format diet or exercise content into HTML"""
    if not content:
        return ''
    
    lines = content.split('\n')
    formatted_lines = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('-') or line.startswith('•'):
            if not in_list:
                formatted_lines.append('<ul>')
                in_list = True
            line_content = line[1:].strip()
            line_content = re.sub(r'(\d+%)', r'<strong>\1</strong>', line_content)
            line_content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', line_content)
            formatted_lines.append(f'<li>{line_content}</li>')
        elif 'summary' in line.lower():
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            summary_text = re.sub(r'.*[Ss]ummary[：:]\s*', '', line)
            formatted_lines.append(f'<div class="lifestyle-summary">{summary_text}</div>')
        else:
            if in_list:
                formatted_lines.append('</ul>')
                in_list = False
            formatted_lines.append(f'<p>{line}</p>')
    
    if in_list:
        formatted_lines.append('</ul>')
    
    content_html = '\n'.join(formatted_lines)
    
    return f'''
    <div class="lifestyle-section">
        <h2><span class="icon">{icon}</span> {title}</h2>
        <div class="lifestyle-content">
            {content_html}
        </div>
    </div>
    '''

def create_risk_card(risk):
    """Create risk card HTML"""
    level_class = f'risk-{risk["level"].lower()}'
    level_text = risk['level'].upper()
    
    suggestions_html = ''
    for sug in risk['suggestions']:
        evidence_html = ''
        if sug['evidence']:
            evidence_html = f'<div class="evidence"><span class="evidence-label">Literature Support:</span> {sug["evidence"]}</div>'
        if sug['reasoning']:
            evidence_html += f'<div class="evidence"><span class="evidence-label">Reasoning:</span> {sug["reasoning"]}</div>'
        
        suggestions_html += f'''
        <div class="suggestion-item">
            <div class="suggestion-content">
                <span class="suggestion-number">{sug['number']}</span>
                {sug['content']}
            </div>
            {evidence_html}
        </div>
        '''
    
    return f'''
    <div class="risk-card">
        <div class="risk-header">
            <div class="disease-name">{risk['disease']}</div>
            <div class="risk-level {level_class}">Risk: {level_text}</div>
        </div>
        <div class="suggestions">
            {suggestions_html}
        </div>
    </div>
    '''

def extract_overall_suggestions(content):
    """
    Return ONLY the '### Overall Overview' block.
    It starts at the heading itself and ends BEFORE '### Detailed Analysis'
    (or, if missing, before the next H3 heading / score header).
    """
    import re

    # We prefer this one explicitly
    prefer = '### Overall Overview'
    # Fallback headings if "Overall Overview" isn't present in some templates
    fallbacks = [
        '### General Overview',
        '### Summary and Encouragement',
        '-----Final Recommendations----',
    ]

    # Anything that must stop the slice if it appears after the start
    end_markers = [
        '### Detailed Analysis',
        '### Personalized Recommendations',
        '### Your health score:',
    ]

    def slice_from(marker: str):
        start = content.find(marker)
        if start == -1:
            return None

        # Start AFTER the heading line itself
        # (keep the heading’s following text only)
        start_line_end = content.find('\n', start)
        if start_line_end == -1:
            start_line_end = start + len(marker)

        # Collect candidate end positions from known markers
        candidates = []
        for m in end_markers:
            idx = content.find(m, start_line_end)
            if idx != -1:
                candidates.append(idx)

        # Generic: the next H3 heading (### ) after start will also terminate
        h3_match = re.search(r'\n###\s+', content[start_line_end:])
        if h3_match:
            candidates.append(start_line_end + h3_match.start())

        # If nothing else, cut at end of document
        end = min(candidates) if candidates else len(content)

        return content[start_line_end:end].strip()

    # Prefer the exact "Overall Overview" block
    out = slice_from(prefer)

    # If not found, try fallbacks
    if out is None:
        for mk in fallbacks:
            out = slice_from(mk)
            if out:
                break

    return out or ''

def extract_lifestyle_risk_assessment(content):
    """Extract Lifestyle Risk Assessment section"""
    marker = '## Lifestyle Risk Assessment'

    if marker not in content:
        return ''

    start_idx = content.index(marker)

    # Find end markers - next H2 section or end of content
    end_markers = ['\n## ', '\n### Your health score:', '\n-----']
    end_idx = len(content)

    for end_marker in end_markers:
        if end_marker in content[start_idx + len(marker):]:
            temp_idx = content.index(end_marker, start_idx + len(marker))
            end_idx = min(end_idx, temp_idx)

    lifestyle_content = content[start_idx:end_idx].strip()
    return lifestyle_content

def format_lifestyle_risk_html(lifestyle_content):
    """Format lifestyle risk assessment into HTML - simplified format for top 5 traits"""
    if not lifestyle_content:
        return ''

    html_parts = ['<div class="lifestyle-risk-section">']
    html_parts.append('<h2>🌟 Lifestyle Risk Assessment</h2>')

    # Extract the introductory text (everything before the first **trait**)
    intro_match = re.search(r'## Lifestyle Risk Assessment\s*\n\s*(.+?)(?=\n\*\*)', lifestyle_content, re.DOTALL)
    if intro_match:
        intro_text = intro_match.group(1).strip()
        html_parts.append(f'<p style="text-align: center; color: #64748b; margin-bottom: 20px;">{intro_text}</p>')

    # Parse individual trait items - format: **trait_name**\n- Risk Score: ...\n- Percentile: ...\n- advice...
    # Split by **trait_name** pattern (no Chinese name anymore)
    trait_pattern = r'\*\*([^*]+)\*\*\s*\n((?:- [^\n]+\n?)+)'
    matches = re.finditer(trait_pattern, lifestyle_content)

    for match in matches:
        trait_name = match.group(1).strip()
        details = match.group(2).strip()

        # Extract details
        risk_score = ''
        percentile = ''
        description = ''

        for line in details.split('\n'):
            line = line.strip()
            if line.startswith('- Risk Score:'):
                risk_score = line.replace('- Risk Score:', '').strip()
            elif line.startswith('- Percentile:'):
                percentile = line.replace('- Percentile:', '').strip()
            elif line.startswith('- '):
                description = line[2:].strip()

        html_parts.append('<div class="lifestyle-risk-item">')
        html_parts.append(f'<h4>{trait_name}</h4>')
        # Only show percentile (risk_score removed as per requirement)
        if percentile:
            html_parts.append(f'<div class="risk-info"><strong>Percentile:</strong> {percentile}</div>')
        if description:
            html_parts.append(f'<div class="risk-description">{description}</div>')
        html_parts.append('</div>')

    html_parts.append('</div>')
    return '\n'.join(html_parts)

def generate_pdf(txt_file_path, pdf_file_path, extra_text=''):
    """Generate English PDF report"""
    with open(txt_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
        # NEW: dump the raw text to logs for debugging
    print("===== [pdfGeneration] RAW INPUT TEXT START =====")
    print(content)
    print("===== [pdfGeneration] RAW INPUT TEXT END =====")
    print(f"Content length: {len(content)} characters")
    
    # Debug: Print what we're working with
    print(f"Content length: {len(content)} characters")
    
    # Extract components
    health_scores = extract_health_scores(content)
    print(f"Found {len(health_scores)} health scores")
    
    risks = parse_disease_risks(content)
    print(f"Found {len(risks)} disease risks with recommendations")
    for risk in risks:
        print(f"  - {risk['disease']}: {risk['level']} ({len(risk['suggestions'])} suggestions)")
    
    # Generate HTML sections
    health_scores_html = format_health_scores_html(health_scores)
    
    risk_cards_html = ''
    for risk in risks:
        risk_cards_html += create_risk_card(risk)
    
    if not risk_cards_html:
        risk_cards_html = '<div class="risk-card"><p>No specific disease risks require attention at this time.</p></div>'
    
    diet_content = extract_diet_analysis(content)
    diet_html = format_lifestyle_content(diet_content, 'Dietary Habits Analysis', '🍽️')
    
    exercise_content = extract_exercise_analysis(content)
    exercise_html = format_lifestyle_content(exercise_content, 'Exercise Habits Analysis', '🏃')
    
    overall_content = extract_overall_suggestions(content)
    overall_html = ''
    if overall_content:
        overall_html = f'''
        <div class="overall-section">
            <h2>💡 Comprehensive Health Recommendations</h2>
            <div class="overall-content">
                {overall_content.replace(chr(10), '<br>')}
            </div>
        </div>
        '''

    # Extract and format lifestyle risk assessment
    lifestyle_content = extract_lifestyle_risk_assessment(content)
    lifestyle_html = format_lifestyle_risk_html(lifestyle_content)
    if lifestyle_html:
        print(f"Found Lifestyle Risk Assessment section")
    else:
        print("No Lifestyle Risk Assessment section found")

    # Fill template
    replacements = {
        '{{report_date}}': datetime.now().strftime('%B %d, %Y'),
        '{{generation_time}}': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        '{{health_scores}}': health_scores_html,
        '{{diet_analysis}}': diet_html,
        '{{exercise_analysis}}': exercise_html,
        '{{risk_cards}}': risk_cards_html,
        '{{overall_suggestions}}': overall_html,
        '{{lifestyle_risk}}': lifestyle_html,
    }
    
    html_content = HTML_TEMPLATE
    for k, v in replacements.items():
        html_content = html_content.replace(k, v)
    
    # Generate PDF
    HTML(string=html_content).write_pdf(pdf_file_path)
    print(f"PDF report generated: {pdf_file_path}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python pdfGeneration_english.py <text_file_path> <pdf_output_path> [extra_text]")
        sys.exit(1)
    
    txt_file = sys.argv[1]
    pdf_file = sys.argv[2]
    extra_text = sys.argv[3] if len(sys.argv) > 3 else ''
    
    try:
        import weasyprint
    except ImportError:
        print("Please install weasyprint first: pip install weasyprint")
        sys.exit(1)
    
    generate_pdf(txt_file, pdf_file, extra_text)