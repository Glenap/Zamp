CREATE TABLE `documents` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`submission_id` text NOT NULL,
	`filename` text NOT NULL,
	`path` text NOT NULL,
	`doc_type_detected` text,
	FOREIGN KEY (`submission_id`) REFERENCES `submissions`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `documents_submission` ON `documents` (`submission_id`);--> statement-breakpoint
CREATE TABLE `messages_outbox` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`run_id` integer NOT NULL,
	`audience` text NOT NULL,
	`subject` text NOT NULL,
	`body` text NOT NULL,
	`sent_at` text,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `overrides` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`run_id` integer NOT NULL,
	`reason` text NOT NULL,
	`old_status` text NOT NULL,
	`new_status` text NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `runs` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`submission_id` text NOT NULL,
	`parent_run_id` integer,
	`status` text NOT NULL,
	`risk_score` real,
	`decision_json` text,
	`started_at` text,
	`finished_at` text,
	FOREIGN KEY (`submission_id`) REFERENCES `submissions`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `runs_submission` ON `runs` (`submission_id`);--> statement-breakpoint
CREATE TABLE `settings` (
	`key` text PRIMARY KEY NOT NULL,
	`value_json` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `stage_results` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`run_id` integer NOT NULL,
	`stage_no` integer NOT NULL,
	`stage_name` text NOT NULL,
	`stage_type` text NOT NULL,
	`status` text NOT NULL,
	`input_json` text,
	`output_json` text,
	`started_at` text,
	`duration_ms` real,
	`rule_version` text,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `stages_run` ON `stage_results` (`run_id`);--> statement-breakpoint
CREATE TABLE `submissions` (
	`id` text PRIMARY KEY NOT NULL,
	`parent_submission_id` text,
	`form_json` text NOT NULL,
	`created_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `vendors_existing` (
	`id` integer PRIMARY KEY NOT NULL,
	`legal_name` text NOT NULL,
	`trade_name` text,
	`country` text NOT NULL,
	`tax_id` text,
	`bank_account` text,
	`iban` text,
	`status` text NOT NULL,
	`email_domain` text,
	`created_at` text NOT NULL
);
