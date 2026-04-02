export interface ParamRow {
  name: string;
  type: string;
  required: boolean;
  default: unknown;
  has_default: boolean;
  default_display: string;
  description: string;
}

export interface OutputRow {
  name: string;
  type: string;
  description: string;
}

export interface Tool {
  name: string;
  description: string;
  summary: string;
  param_rows: ParamRow[];
  output_rows: OutputRow[];
  required_count: number;
  optional_count: number;
  call_html: string;
  response_html: string;
  session_assumptions: string | null;
  example_layout: "default" | "apps";
  example_screenshot: { src: string; alt: string; caption: string } | null;
}

export interface Subgroup {
  label: string | null;
  tools: Tool[];
}

export interface ToolGroup {
  id: string;
  label: string;
  blurb: string;
  subgroups: Subgroup[];
}

export interface EditionColumn {
  key: string;
  label: string;
  class_name: string;
}

export interface EditionGroup {
  id: string;
  label: string;
  summary: string;
  columns: EditionColumn[];
  rows: Record<string, unknown>[];
}

export interface UsageShowcase {
  id: string;
  title: string;
  category?: string;
  prompt_html: string;
  model?: string;
  date?: string;
  prerequisite_tools?: string[];
  tools: string[];
  response_html: string;
  generated?: boolean;
}

export interface UsageExample {
  id: string;
  title: string;
  prompt_html: string;
  tools: string[];
}

export interface DocsData {
  groups: ToolGroup[];
  flat_tools: Tool[];
  edition_groups: EditionGroup[];
  usage_examples: {
    showcases: UsageShowcase[];
    examples: UsageExample[];
  };
  tool_count: number;
  group_count: number;
  tafsir_count: number;
  quickstart_config: string;
  quickstart_config_html: string;
}
