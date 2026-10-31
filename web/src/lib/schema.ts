import { z } from "zod";

export const pitchSchema = z.object({
  currency: z.string(),
  pilotAmountInr: z.number(),
  previousDeckAmountInr: z.number(),
  timelineDays: z.number(),
  reconcileNote: z.string(),
  showReconcileNote: z.boolean().optional(),
  whyPilot: z.string(),
  unlocks: z.array(z.string()),
  timeline: z.array(z.object({ days: z.string(), label: z.string() })),
  validated: z.array(z.string()),
  notValidated: z.array(z.string()),
});

export const bootstrapSchema = z
  .object({
    ok: z.boolean(),
    ready: z.boolean().optional(),
    pitch: pitchSchema,
    synthetic_label: z.string().optional(),
    engine_version: z.string().optional(),
    categories: z.record(z.any()).optional(),
    factory: z.any().optional(),
    period: z.any().optional(),
    snapshot: z.any().nullable().optional(),
    stale: z.boolean().optional(),
    results: z.array(z.any()).optional(),
    activities: z.array(z.any()).optional(),
    factors: z.array(z.any()).optional(),
    snapshots: z.array(z.any()).optional(),
    report_markdown: z.string().nullable().optional(),
    sample_csv: z.string().optional(),
    sample_csv_with_errors: z.string().optional(),
    hand_check: z.any().optional(),
    sample_previews: z.any().optional(),
    created_snapshot_id: z.number().optional(),
    import_result: z.any().optional(),
    gap_closed: z.boolean().optional(),
  })
  .passthrough();

export type Bootstrap = z.infer<typeof bootstrapSchema>;
export type Pitch = z.infer<typeof pitchSchema>;

export const importPreviewSchema = z
  .object({
    ok: z.boolean(),
    header_errors: z.array(z.string()).optional(),
    ignored_columns: z.array(z.string()).optional(),
    rows: z.array(z.any()).optional(),
    n_rows: z.number().optional(),
    n_valid: z.number().optional(),
    n_rejected: z.number().optional(),
    filename: z.string().optional(),
    errors: z.array(z.string()).optional(),
  })
  .passthrough();

export const whatIfSchema = z
  .object({
    ok: z.boolean(),
    result_id: z.number().optional(),
    quantity_before: z.any().optional(),
    quantity_after: z.any().optional(),
    unit: z.string().optional(),
    kg_before: z.number().nullable().optional(),
    kg_after: z.number().nullable().optional(),
    status: z.string().optional(),
    plain_formula: z.string().nullable().optional(),
    engine_formula: z.string().nullable().optional(),
    category_kg_before: z.number().nullable().optional(),
    category_kg_after: z.number().nullable().optional(),
    total_kg_before: z.number().nullable().optional(),
    total_kg_after: z.number().nullable().optional(),
    errors: z.array(z.string()).optional(),
  })
  .passthrough();
