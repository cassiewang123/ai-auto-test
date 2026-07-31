export type JsonDiffKind = 'added' | 'removed' | 'changed' | 'type_changed';

export interface JsonDifference {
  path: string;
  kind: JsonDiffKind;
  left?: unknown;
  right?: unknown;
}

export interface JsonCompareOptions {
  ignoreArrayOrder?: boolean;
}

function typeOf(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).sort().join(',')}]`;
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(record[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

function pathForKey(parentPath: string, key: string): string {
  return /^[A-Za-z_$][\w$]*$/.test(key)
    ? `${parentPath}.${key}`
    : `${parentPath}[${JSON.stringify(key)}]`;
}

function normalizeArray(value: unknown[], ignoreArrayOrder: boolean): unknown[] {
  return ignoreArrayOrder
    ? [...value].sort((left, right) => stableJson(left).localeCompare(stableJson(right)))
    : value;
}

function compareValue(
  left: unknown,
  right: unknown,
  path: string,
  differences: JsonDifference[],
  options: JsonCompareOptions
): void {
  if (Object.is(left, right)) return;

  const leftType = typeOf(left);
  const rightType = typeOf(right);
  if (leftType !== rightType) {
    differences.push({ path, kind: 'type_changed', left, right });
    return;
  }

  if (Array.isArray(left) && Array.isArray(right)) {
    const normalizedLeft = normalizeArray(left, Boolean(options.ignoreArrayOrder));
    const normalizedRight = normalizeArray(right, Boolean(options.ignoreArrayOrder));
    const count = Math.max(normalizedLeft.length, normalizedRight.length);
    for (let index = 0; index < count; index += 1) {
      const childPath = `${path}[${index}]`;
      if (index >= normalizedLeft.length) {
        differences.push({
          path: childPath,
          kind: 'added',
          right: normalizedRight[index],
        });
      } else if (index >= normalizedRight.length) {
        differences.push({
          path: childPath,
          kind: 'removed',
          left: normalizedLeft[index],
        });
      } else {
        compareValue(
          normalizedLeft[index],
          normalizedRight[index],
          childPath,
          differences,
          options
        );
      }
    }
    return;
  }

  if (
    leftType === 'object' &&
    rightType === 'object' &&
    left !== null &&
    right !== null
  ) {
    const leftRecord = left as Record<string, unknown>;
    const rightRecord = right as Record<string, unknown>;
    const keys = new Set([...Object.keys(leftRecord), ...Object.keys(rightRecord)]);
    Array.from(keys)
      .sort()
      .forEach((key) => {
        const childPath = pathForKey(path, key);
        if (!(key in leftRecord)) {
          differences.push({ path: childPath, kind: 'added', right: rightRecord[key] });
        } else if (!(key in rightRecord)) {
          differences.push({ path: childPath, kind: 'removed', left: leftRecord[key] });
        } else {
          compareValue(leftRecord[key], rightRecord[key], childPath, differences, options);
        }
      });
    return;
  }

  differences.push({ path, kind: 'changed', left, right });
}

export function compareJson(
  left: unknown,
  right: unknown,
  options: JsonCompareOptions = {}
): JsonDifference[] {
  const differences: JsonDifference[] = [];
  compareValue(left, right, '$', differences, options);
  return differences;
}

export function jsonDiffLabel(kind: JsonDiffKind): string {
  const labels: Record<JsonDiffKind, string> = {
    added: '新增',
    removed: '删除',
    changed: '修改',
    type_changed: '类型变化',
  };
  return labels[kind];
}
