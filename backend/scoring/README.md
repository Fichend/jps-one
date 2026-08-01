# JPS Lead Scoring

This module converts `获客评分标准.xlsx` into deterministic backend scoring rules.

## Scope

- Score merged `candidate_pool` records before they are ranked.
- Preserve evidence-based behavior: missing evidence receives zero or conservative points.
- Expose `jps_score`, `lead_grade`, `score_breakdown`, and `scoring_version` on each candidate.

## Dimensions

- 完整公司注册名称: 10
- 企业邮箱: 12
- 联系电话: 12
- 主营产品匹配度: 16
- 公司官网: 10
- 成立时长: 12
- 实体经营形态: 10
- 决策人信息: 8
- 合规资质: 10

Grades follow the Excel standard: `A >= 80`, `B = 60-79`, `C = 40-59`, `D < 40`.

## Safety Notes

- The scorer does not guess emails, phones, founding dates, licenses, or decision makers.
- Social-only profiles receive lower website points than independent official websites.
- Product fit and compliance points require visible text evidence from candidate fields or evidence items.
