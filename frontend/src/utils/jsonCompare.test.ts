import { describe, expect, it } from 'vitest';
import { compareJson } from './jsonCompare';

describe('compareJson', () => {
  it('reports added, removed, changed, and type-changed values by JSON path', () => {
    const differences = compareJson(
      {
        stable: true,
        removed: 'old',
        changed: 1,
        typeChanged: 1,
      },
      {
        stable: true,
        added: 'new',
        changed: 2,
        typeChanged: '1',
      }
    );

    expect(differences).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ path: '$.added', kind: 'added', right: 'new' }),
        expect.objectContaining({ path: '$.removed', kind: 'removed', left: 'old' }),
        expect.objectContaining({ path: '$.changed', kind: 'changed', left: 1, right: 2 }),
        expect.objectContaining({
          path: '$.typeChanged',
          kind: 'type_changed',
          left: 1,
          right: '1',
        }),
      ])
    );
  });

  it('can ignore array order while preserving default positional comparison', () => {
    expect(compareJson([1, 2], [2, 1])).not.toHaveLength(0);
    expect(compareJson([1, 2], [2, 1], { ignoreArrayOrder: true })).toHaveLength(0);
  });
});
