const API_BASE_URL = "https://danishs-macbook-pro.tail79ab0c.ts.net";

export async function fetchLocationPredictions(query: string) {
  if (!query.trim()) return [];
  
  try {
    const res = await fetch(`${API_BASE_URL}/api/places/autocomplete?query=${encodeURIComponent(query)}`);
    const data = await res.json();
    return data.predictions || [];
  } catch (err) {
    console.error("Error fetching places:", err);
    return [];
  }
}