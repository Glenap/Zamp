import { sqliteTable, text, integer, real, index } from 'drizzle-orm/sqlite-core';

export const vendors = sqliteTable('vendors_existing', {
  id: integer('id').primaryKey(), legalName: text('legal_name').notNull(), tradeName: text('trade_name'),
  country: text('country').notNull(), taxId: text('tax_id'), bankAccount: text('bank_account'),
  iban: text('iban'), status: text('status').notNull(), emailDomain: text('email_domain'), createdAt: text('created_at').notNull(),
});
export const submissions = sqliteTable('submissions', {
  id: text('id').primaryKey(), parentSubmissionId: text('parent_submission_id'), formJson: text('form_json').notNull(),
  createdAt: text('created_at').notNull(),
});
export const documents = sqliteTable('documents', {
  id: integer('id').primaryKey({ autoIncrement: true }), submissionId: text('submission_id').notNull().references(() => submissions.id),
  filename: text('filename').notNull(), path: text('path').notNull(), docTypeDetected: text('doc_type_detected'),
}, t => [index('documents_submission').on(t.submissionId)]);
export const runs = sqliteTable('runs', {
  id: integer('id').primaryKey({ autoIncrement: true }), submissionId: text('submission_id').notNull().references(() => submissions.id),
  parentRunId: integer('parent_run_id'), status: text('status').notNull(), riskScore: real('risk_score'),
  decisionJson: text('decision_json'), startedAt: text('started_at'), finishedAt: text('finished_at'),
}, t => [index('runs_submission').on(t.submissionId)]);
export const stages = sqliteTable('stage_results', {
  id: integer('id').primaryKey({ autoIncrement: true }), runId: integer('run_id').notNull().references(() => runs.id),
  stageNo: integer('stage_no').notNull(), stageName: text('stage_name').notNull(), stageType: text('stage_type').notNull(),
  status: text('status').notNull(), inputJson: text('input_json'), outputJson: text('output_json'),
  startedAt: text('started_at'), durationMs: real('duration_ms'), ruleVersion: text('rule_version'),
}, t => [index('stages_run').on(t.runId)]);
export const messages = sqliteTable('messages_outbox', {
  id: integer('id').primaryKey({ autoIncrement: true }), runId: integer('run_id').notNull().references(() => runs.id),
  audience: text('audience').notNull(), subject: text('subject').notNull(), body: text('body').notNull(), sentAt: text('sent_at'),
});
export const overrides = sqliteTable('overrides', {
  id: integer('id').primaryKey({ autoIncrement: true }), runId: integer('run_id').notNull().references(() => runs.id),
  reason: text('reason').notNull(), oldStatus: text('old_status').notNull(), newStatus: text('new_status').notNull(),
  createdAt: text('created_at').notNull(),
});
export const settings = sqliteTable('settings', { key: text('key').primaryKey(), valueJson: text('value_json').notNull() });
