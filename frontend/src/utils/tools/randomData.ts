export type DataKind =
  | 'name'
  | 'email'
  | 'phone'
  | 'idCard'
  | 'ip'
  | 'address'
  | 'company'
  | 'uuid'
  | 'bankCard'
  | 'date';

const surnames = ['王', '李', '张', '刘', '陈', '杨', '赵', '黄', '周', '吴', '徐', '孙'];
const givenNames = ['伟', '芳', '娜', '敏', '静', '磊', '强', '军', '洋', '勇', '艳', '杰'];
const cities = ['北京市 朝阳区', '上海市 浦东新区', '广东省 深圳市 南山区', '浙江省 杭州市 西湖区', '四川省 成都市 高新区'];
const streets = ['科技路', '建设大道', '中山路', '人民路', '解放路', '创业大街'];
const companies = ['智测科技', '云启软件', '恒信数据', '锐思网络', '弘远信息'];
const domains = ['example.com', 'testmail.com', 'demo.org', 'sample.net'];

function randomInt(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function pick<T>(items: T[]): T {
  return items[randomInt(0, items.length - 1)];
}

export function generateData(kind: DataKind, count: number): string[] {
  const total = Math.max(1, Math.min(1000, Math.floor(count)));
  return Array.from({ length: total }, () => {
    if (kind === 'name') return `${pick(surnames)}${pick(givenNames)}`;
    if (kind === 'email') {
      return `test${randomInt(1000, 999999)}@${pick(domains)}`;
    }
    if (kind === 'phone') {
      return `1${randomInt(3, 9)}${String(randomInt(0, 999999999)).padStart(9, '0')}`;
    }
    if (kind === 'ip') {
      return `${randomInt(1, 223)}.${randomInt(0, 255)}.${randomInt(0, 255)}.${randomInt(1, 254)}`;
    }
    if (kind === 'address') {
      return `${pick(cities)}${pick(streets)}${randomInt(1, 999)}号`;
    }
    if (kind === 'company') {
      return `${pick(companies)}有限公司`;
    }
    if (kind === 'uuid') {
      return crypto.randomUUID();
    }
    if (kind === 'bankCard') {
      return `62${String(randomInt(0, Number.MAX_SAFE_INTEGER)).padStart(16, '0')}`.slice(
        0,
        18
      );
    }
    if (kind === 'date') {
      const start = new Date(2020, 0, 1).getTime();
      const end = new Date(2026, 11, 31).getTime();
      return new Date(randomInt(start, end)).toISOString().slice(0, 10);
    }
    const year = randomInt(1970, 2005);
    const month = String(randomInt(1, 12)).padStart(2, '0');
    const day = String(randomInt(1, 28)).padStart(2, '0');
    return `110101${year}${month}${day}${String(randomInt(0, 9999)).padStart(4, '0')}`;
  });
}
