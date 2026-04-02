<script lang="ts">
  import type { ToolGroup, UsageShowcase } from "./types";

  interface Props {
    groups: ToolGroup[];
    showcases: UsageShowcase[];
    activeId: string;
  }

  let { groups, showcases, activeId }: Props = $props();
</script>

<aside class="sidebar" id="sidebar" aria-label="On this page">
  <div class="sidebar-header">
    <a href="https://quran.ai" class="logo">quran<span class="ai">.ai</span></a>
  </div>
  <nav class="sidebar-nav">
    <a href="#top" class:active={activeId === 'top' || activeId === 'hero'}>Documentation</a>
    <a href="#setup-and-connect" class:active={activeId === 'setup-and-connect'}>Setup and connect</a>
    <div class="sidebar-group">
      <a class="sidebar-link-level-2" href="#setup-at-a-glance" class:active={activeId === 'setup-at-a-glance'}>At a glance</a>
      <a class="sidebar-link-level-2" href="#setup-claude" class:active={activeId === 'setup-claude'}>Claude</a>
      <a class="sidebar-link-level-2" href="#setup-chatgpt" class:active={activeId === 'setup-chatgpt'}>ChatGPT</a>
      <a class="sidebar-link-level-2" href="#setup-other-clients" class:active={activeId === 'setup-other-clients'}>Other MCP clients</a>
    </div>
    <a href="#usage-examples" class:active={activeId === 'usage-examples'}>Usage examples</a>
    {#if showcases.length > 0}
      <div class="sidebar-group">
        {#each showcases as showcase}
          <a class="sidebar-link-level-2" href="#{showcase.id}" class:active={activeId === showcase.id}>{showcase.category || showcase.title}</a>
        {/each}
      </div>
    {/if}
    <a href="#available-tools" class:active={activeId === 'available-tools'}>Tool reference</a>
    {#each groups as group}
      <div class="sidebar-group">
        <span class="sidebar-group-label">{group.label}</span>
        {#each group.subgroups as subgroup}
          {#if subgroup.label}
            <span class="sidebar-subgroup-label">{subgroup.label}</span>
          {/if}
          {#each subgroup.tools as tool}
            <a
              class="{subgroup.label ? 'sidebar-link-level-3' : 'sidebar-link-level-2'} sidebar-tool-link"
              href="#{tool.name}"
              class:active={activeId === tool.name}
            >{tool.name}</a>
          {/each}
        {/each}
      </div>
    {/each}
    <a href="#editions" class:active={activeId === 'editions'}>Supported editions</a>
    <a href="#troubleshooting" class:active={activeId === 'troubleshooting'}>Troubleshooting</a>
    <a href="#notes" class:active={activeId === 'notes'}>Notes</a>
  </nav>
</aside>
