import type { Logger, McpbManifest, McpbUserConfigValues, McpServerConfig } from "../types.js";
/**
 * This file contains utility functions for handling MCPB configuration,
 * including variable replacement and MCP server configuration generation.
 */
/**
 * Recursively replaces variables in any value. Handles strings, arrays, and objects.
 *
 * @param value The value to process
 * @param variables Object containing variable replacements
 * @returns The processed value with all variables replaced
 */
export declare function replaceVariables(value: unknown, variables: Record<string, string | string[]>): unknown;
interface GetMcpConfigForManifestOptions {
    manifest: McpbManifest;
    extensionPath: string;
    systemDirs: Record<string, string>;
    userConfig: McpbUserConfigValues;
    pathSeparator: string;
    logger?: Logger;
}
export declare function getMcpConfigForManifest(options: GetMcpConfigForManifestOptions): Promise<McpServerConfig | undefined>;
interface HasRequiredConfigMissingOptions {
    manifest: McpbManifest;
    userConfig?: McpbUserConfigValues;
}
/**
 * Check if an extension has missing required configuration
 * @param manifest The extension manifest
 * @param userConfig The user configuration
 * @returns true if required configuration is missing
 */
export declare function hasRequiredConfigMissing({ manifest, userConfig, }: HasRequiredConfigMissingOptions): boolean;
export {};
