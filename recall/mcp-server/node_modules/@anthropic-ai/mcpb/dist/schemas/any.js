import * as z from "zod";
import * as v0_1 from "./0.1.js";
import * as v0_2 from "./0.2.js";
import * as v0_3 from "./0.3.js";
/**
 * Union schema that accepts any supported manifest version (0.1, 0.2, 0.3).
 * Use this when you need to validate manifests of any version.
 */
export const McpbManifestSchema = z.union([
    v0_1.McpbManifestSchema,
    v0_2.McpbManifestSchema,
    v0_3.McpbManifestSchema,
]);
