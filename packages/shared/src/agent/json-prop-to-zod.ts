import { z } from 'zod';

function jsonSchemaToZodShape(schema: Record<string, unknown>, depth = 0): Record<string, z.ZodTypeAny> {
  const properties = (schema.properties as Record<string, any>) || {};
  const required = new Set((schema.required as string[]) || []);
  const shape: Record<string, z.ZodTypeAny> = {};

  for (const [key, prop] of Object.entries(properties)) {
    let zodType = jsonPropToZod(prop, depth);
    if (!required.has(key)) zodType = zodType.optional();
    shape[key] = zodType;
  }

  return shape;
}

// jsonPropToZod — salvaged from removed claude-agent.ts (pure utility, no SDK deps)
const MAX_SCHEMA_DEPTH = 5;

export function jsonPropToZod(prop: any, depth = 0): z.ZodTypeAny {
  if (!prop || typeof prop !== 'object') return z.unknown();
  if (depth >= MAX_SCHEMA_DEPTH) return z.unknown();

  // Attach description if present
  const withDesc = (zodType: z.ZodTypeAny): z.ZodTypeAny =>
    prop.description ? zodType.describe(prop.description) : zodType;

  // Enum — string literals
  if (prop.enum && Array.isArray(prop.enum) && prop.enum.length > 0) {
    return withDesc(z.enum(prop.enum as [string, ...string[]]));
  }

  // oneOf / anyOf — discriminated or plain unions
  const unionVariants = prop.oneOf ?? prop.anyOf;
  if (Array.isArray(unionVariants) && unionVariants.length > 0) {
    const members = unionVariants.map((v: any) => jsonPropToZod(v, depth + 1));
    if (members.length === 1) return withDesc(members[0]!);
    return withDesc(z.union(members as [z.ZodTypeAny, z.ZodTypeAny, ...z.ZodTypeAny[]]));
  }

  // allOf — merge into a single object shape
  if (Array.isArray(prop.allOf) && prop.allOf.length > 0) {
    const mergedProps: Record<string, any> = {};
    const mergedRequired: string[] = [];
    for (const sub of prop.allOf) {
      if (sub.properties) Object.assign(mergedProps, sub.properties);
      if (Array.isArray(sub.required)) mergedRequired.push(...sub.required);
    }
    if (Object.keys(mergedProps).length > 0) {
      return withDesc(jsonPropToZod({
        type: 'object',
        properties: mergedProps,
        required: mergedRequired,
        description: prop.description,
      }, depth));
    }
    // Fallback: if allOf doesn't have properties, take the first variant
    return withDesc(jsonPropToZod(prop.allOf[0], depth + 1));
  }

  switch (prop.type) {
    case 'string':
      return withDesc(z.string());
    case 'number':
    case 'integer':
      return withDesc(z.number());
    case 'boolean':
      return withDesc(z.boolean());
    case 'array': {
      const itemSchema = prop.items
        ? jsonPropToZod(prop.items, depth + 1)
        : z.unknown();
      return withDesc(z.array(itemSchema));
    }
    case 'object': {
      // Nested object with known properties → build z.object({...})
      if (prop.properties && typeof prop.properties === 'object') {
        const shape = jsonSchemaToZodShape(prop, depth + 1);
        const obj = z.object(shape);
        // JSON Schema defaults additionalProperties to true when omitted.
        // Only use strict (strip) mode when explicitly set to false.
        if (prop.additionalProperties === false) {
          return withDesc(obj);
        }
        return withDesc(obj.passthrough());
      }
      // Generic object (no properties defined)
      return withDesc(z.record(z.string(), z.unknown()));
    }
    default:
      return withDesc(z.unknown());
  }
}
