<script lang="ts">
  import type { EditionGroup } from "./types";

  interface Props {
    group: EditionGroup;
  }

  let { group }: Props = $props();

  function copyText(btn: HTMLButtonElement) {
    const text = btn.dataset.copy ?? btn.textContent ?? "";
    navigator.clipboard.writeText(text);
  }
</script>

<div
  class="edition-group docs-collapsible"
  id="editions-{group.id}"
  data-collapsible
  data-collapsed-max="31rem"
  data-auto-collapse="always"
>
  <h3 class="edition-group-heading">{group.label}</h3>
  <p class="edition-group-count">{group.summary}</p>
  <table class="edition-table">
    <thead>
      <tr>
        {#each group.columns as col}
          <th>{col.label}</th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each group.rows as row}
        <tr>
          {#each group.columns as col}
            <td>
              {#if col.key === "edition_id"}
                <button
                  type="button"
                  class="copy-cell"
                  data-copy={String(row[col.key] ?? "")}
                  onclick={(e) => copyText(e.currentTarget as HTMLButtonElement)}
                >{row[col.key]}</button>
              {:else if col.key === "name"}
                <span class="ed-name">{row[col.key]}</span>
              {:else if col.key === "author"}
                <span class="ed-author">{row[col.key] ?? '—'}</span>
              {:else if col.key === "lang"}
                <span class="ed-lang">{row[col.key]}</span>
              {:else}
                {row[col.key] ?? '—'}
              {/if}
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>
