export interface CountryInfo {
  population: number;
  capital: string | null;
  borders: string[];
  languages: string[];
}

const _cache = new Map<string, CountryInfo | null>();

export async function fetchCountryInfo(countryName: string): Promise<CountryInfo | null> {
  const key = countryName.toLowerCase();
  if (_cache.has(key)) return _cache.get(key)!;

  try {
    const res = await fetch(
      `https://restcountries.com/v3.1/name/${encodeURIComponent(countryName)}?fullText=true&fields=population,capital,borders,languages`,
    );
    if (!res.ok) {
      _cache.set(key, null);
      return null;
    }
    const data = await res.json();
    const c = Array.isArray(data) ? data[0] : null;
    if (!c) {
      _cache.set(key, null);
      return null;
    }
    const info: CountryInfo = {
      population: c.population ?? 0,
      capital: Array.isArray(c.capital) && c.capital.length > 0 ? c.capital[0] : null,
      borders: Array.isArray(c.borders) ? c.borders : [],
      languages: c.languages ? Object.values(c.languages as Record<string, string>) : [],
    };
    _cache.set(key, info);
    return info;
  } catch {
    _cache.set(key, null);
    return null;
  }
}

export function formatPopulation(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}
