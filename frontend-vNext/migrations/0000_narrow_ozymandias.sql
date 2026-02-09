CREATE TABLE "backend_vnext"."usdm_documents" (
	"id" serial PRIMARY KEY NOT NULL,
	"study_id" varchar(255) NOT NULL,
	"study_title" text NOT NULL,
	"usdm_data" jsonb NOT NULL,
	"source_document_url" text NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "usdm_documents_study_id_unique" UNIQUE("study_id")
);
--> statement-breakpoint
CREATE TABLE "backend_vnext"."usdm_edit_audit" (
	"id" serial PRIMARY KEY NOT NULL,
	"document_id" integer NOT NULL,
	"study_id" varchar(255) NOT NULL,
	"study_title" text,
	"field_path" varchar(500) NOT NULL,
	"original_value" jsonb,
	"new_value" jsonb,
	"original_usdm" jsonb,
	"updated_usdm" jsonb,
	"updated_by" varchar(255) NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "backend_vnext"."usdm_edit_audit" ADD CONSTRAINT "usdm_edit_audit_document_id_usdm_documents_id_fk" FOREIGN KEY ("document_id") REFERENCES "backend_vnext"."usdm_documents"("id") ON DELETE no action ON UPDATE no action;