/**
 * ZenSkill Event Adapter
 *
 * Translates ZenSkill's AgentEvent stream (from agent-engine serve JSONL)
 * into Craft AgentEvent format for UI compatibility.
 *
 * Event mapping (source: docs/zenskill_backend_reference.md):
 * - TextDelta → text_delta
 * - ToolExecutionStart → tool_start
 * - ToolExecutionEnd → tool_result
 * - MessageEnd(stop_reason=error) → error
 * - MessageEnd(stop_reason=stop, with text) → text_complete
 * - AgentEnd → complete
 */

import type { AgentEvent as CraftAgentEvent } from '@craft-agent/core/types';

/**
 * ZenSkill event types (from zenskill/runtime/agent/types.py)
 */
type ZenSkillEventType =
  | 'agent_start' | 'agent_end'
  | 'turn_start' | 'turn_end'
  | 'message_start' | 'message_update' | 'message_end'
  | 'tool_execution_start' | 'tool_execution_end' | 'tool_execution_update';

interface ZenSkillEvent {
  type: ZenSkillEventType;
  [key: string]: unknown;
}

/**
 * Adapt a single ZenSkill event to Craft AgentEvent format.
 * Returns null for events that should be silently consumed.
 */
export function adaptZenSkillEvent(event: ZenSkillEvent): CraftAgentEvent | null {
  switch (event.type) {
    // ── Lifecycle (consume silently) ──
    case 'agent_start':
    case 'turn_start':
    case 'turn_end':
    case 'message_start':
      return null;

    // ── Agent end → complete ──
    case 'agent_end': {
      const usage = event.usage as Record<string, number> | undefined;
      if (usage) {
        return {
          type: 'complete',
          usage: {
            inputTokens: usage.input_tokens || 0,
            outputTokens: usage.output_tokens || 0,
          },
        };
      }
      return { type: 'complete' };
    }

    // ── Text streaming ──
    case 'message_update': {
      const delta = event.delta as Record<string, unknown> | undefined;
      if (!delta) return null;
      const deltaKind = (delta.kind || delta.type) as string;
      const deltaText = delta.text as string;
      if ((deltaKind === 'text' || deltaKind === 'TextDelta') && deltaText) {
        return { type: 'text_delta', text: deltaText };
      }
      // thinking_delta is not a valid Craft AgentEvent type — skip
      return null;
    }

    // ── Message end → text_complete or error ──
    case 'message_end': {
      const nested = event.message as Record<string, unknown> | undefined;
      const stopReason = (nested?.stopReason ?? nested?.stop_reason ?? event.stopReason) as string | undefined;
      const errorMessage = (nested?.errorMessage ?? event.error_message) as string | undefined;

      if (stopReason === 'error' || stopReason === 'aborted') {
        return { type: 'error', message: errorMessage || 'Agent error' };
      }

      const textFromNested = nested?.text as string | undefined;
      const textFromTopLevel = event.text as string | undefined;
      const textContent = textFromNested ?? textFromTopLevel;
      const content = nested?.content as Array<Record<string, unknown>> | undefined;

      if (textContent && typeof textContent === 'string' && !Array.isArray(content)) {
        return {
          type: 'text_complete',
          text: textContent,
          isIntermediate: stopReason === 'tool_use',
        };
      }

      if (Array.isArray(content)) {
        const textParts = content
          .filter((c) => c.type === 'TextContent' && c.text)
          .map((c) => c.text as string);
        if (textParts.length > 0) {
          return {
            type: 'text_complete',
            text: textParts.join(''),
            isIntermediate: stopReason === 'tool_use',
          };
        }
      }
      return null;
    }

    // ── Tool events ──
    case 'tool_execution_start':
      return {
        type: 'tool_start',
        toolName: (event.tool_name as string) || 'tool',
        toolUseId: event.tool_call_id as string,
        input: (event.params as Record<string, unknown>) || {},
      };

    case 'tool_execution_end': {
      const result = event.result as Record<string, unknown> | undefined;
      let resultText = '';
      if (result) {
        const content = result.content as Array<Record<string, unknown>> | undefined;
        if (Array.isArray(content)) {
          resultText = content
            .filter((c) => c.type === 'TextContent' && c.text)
            .map((c) => c.text as string)
            .join('');
        } else {
          resultText = String(result);
        }
      }
      return {
        type: 'tool_result',
        toolUseId: event.tool_call_id as string,
        toolName: (event.tool_name as string) || 'tool',
        result: resultText,
        isError: (event.is_error as boolean) || false,
      };
    }

    case 'tool_execution_update':
      return null;

    default:
      return null;
  }
}
