ALTER TABLE "sales" ADD COLUMN "date" timestamp DEFAULT now() NOT NULL;--> statement-breakpoint
ALTER TABLE "purchases" ADD COLUMN "date" timestamp DEFAULT now() NOT NULL;--> statement-breakpoint
UPDATE "sales" SET "date" = "created_at";--> statement-breakpoint
UPDATE "purchases" SET "date" = "created_at";
