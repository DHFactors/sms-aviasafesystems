// Chunk 10 smoke: 31-question master contract + dynamic progress constants.
import { MASTER_QUESTIONS, SURVEY_VERSION } from '../public/survey/default_q.js';

const assert = (cond, msg) => { if (!cond) { console.error('FAIL:', msg); process.exit(1); } console.log('ok -', msg); };

assert(SURVEY_VERSION === '4.0.0', 'SURVEY_VERSION is 4.0.0');
assert(MASTER_QUESTIONS.length === 31, `MASTER_QUESTIONS.length is 31 (got ${MASTER_QUESTIONS.length})`);

const ids = MASTER_QUESTIONS.map(q => q.id);
const v4new = ['q24_accountability','q25_accountability_clear','q26_key_personnel',
               'q27_key_personnel_access','q28_documentation','q29_documentation_current',
               'q30_moc_process','q31_moc_risk'];
for (const id of v4new) assert(ids.includes(id), `contains ${id}`);

// Bilingual completeness + structure on every question.
for (const q of MASTER_QUESTIONS) {
    assert(q.id && q.pillar && q.type && q.text_en && q.text_ne, `structure ok: ${q.id}`);
    assert(['binary', 'likert'].includes(q.type), `${q.id} type valid`);
}

// Pillar coverage matches the four ICAO pillars.
const pillars = new Set(MASTER_QUESTIONS.map(q => q.pillar));
assert(pillars.size === 4, 'four pillars covered');

console.log('ALL CHUNK 10 CONTRACT CHECKS PASSED');
