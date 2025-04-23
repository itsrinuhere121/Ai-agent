import logging
from datetime import datetime
import gradio as gr
import requests
import ollama
from bs4 import BeautifulSoup
import json
from urllib.parse import quote_plus
import time
import random
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('search_debug.log'),
        logging.StreamHandler()
    ]
)
def search_wikipedia(query: str) -> dict:
    logging.info(f"Starting Wikipedia search for: {query}")
    try:
        start_time = datetime.now()
        url = f"https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json"
        }
        response = requests.get(url, params=params)
        logging.info(f"Wikipedia search completed in {(datetime.now() - start_time).total_seconds()}s")
        return response.json()
    
    except Exception as e:
        logging.error(f"Wikipedia search failed: {str(e)}", exc_info=True)
        return {"error": str(e)}

def generate_answer(query: str, combined_results: dict) -> str:
    context = json.dumps(combined_results, indent=2)
    
    # Handle empty results scenario
    if not any(combined_results["sources"].values()):
        return "No search results found. Try rephrasing your question or check your network connection."
        
    prompt = f"""Analyze available information and answer:
    Query: {query}
    Available Context: {context}
    
    If information is conflicting:
    - Prioritize official sources
    - Note disagreements in the answer
    - Maintain neutral tone
    
    Structure your answer with:
    1. Key points
    2. Step-by-step instructions (if applicable)
    3. Common mistakes to avoid"""
    
    try:
        response = ollama.chat(
            model="deepseek-r1:14b",
            messages=[{"role": "user", "content": prompt}]
        )
        return response["message"]["content"]
    except Exception as e:
        return f"Error generating answer: {str(e)}"
def combine_results(query: str, use_google: bool, use_wiki: bool) -> dict:
    combined = {
        "query": query,
        "sources": {
            "google": [],
            "wikipedia": {},
            "fallback": []
        }
    }
    
    try:
        if use_google:
            google_results = search_google(query)
            if not google_results:
                logging.warning("Google failed, using DuckDuckGo fallback")
                combined["sources"]["fallback"] = search_duckduckgo(query)
            else:
                combined["sources"]["google"] = google_results
                
        if use_wiki:
            wiki_data = search_wikipedia(query)
            if "query" in wiki_data:
                combined["sources"]["wikipedia"] = {
                    "results": wiki_data["query"]["search"],
                    "suggestion": wiki_data["query"].get("searchinfo", {}).get("suggestion")
                }
                
        return combined
    
    except Exception as e:
        logging.error(f"Combination failed: {str(e)}")
        return combined
def search_duckduckgo(query: str) -> list:
    """Fallback search engine"""
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": 1,
                "no_redirect": 1
            }
        )
        data = response.json()
        logging.info(f"response received {data}")
        return [{
            "title": data.get("Heading", ""),
            "url": data.get("AbstractURL", ""),
            "snippet": data.get("AbstractText", ""),
            "source": "duckduckgo"
        }]
    except Exception as e:
        logging.error(f"DuckDuckGo fallback failed: {str(e)}")
        return []
    
def search_google(query: str) -> list:

    """Improved Google scraper with multiple fallback methods"""
    logging.info(f"Starting Google search for: {query}")
    base_url = "https://www.google.co.in/search"
    
    params = {
        "q": query,
        "hl": "en",
        "gl": "in",
        "num": 5
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }
    
    try:
        # Add random delay to avoid bot detection
        time.sleep(random.uniform(1.5, 3.0))
        
        response = requests.get(base_url, params=params, headers=headers, timeout=10)
        
        # Improved CAPTCHA detection
        if any(phrase in response.text for phrase in ["CAPTCHA", "unusual traffic", "automated requests"]):
            logging.error("Google blocked request (CAPTCHA detected)")
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        
        # Multiple selector fallbacks
        for result in soup.select('div.g, div[data-snf], div[data-header-feature]'):
            try:
                title = result.select_one('h3, [role="heading"]').text
                url = result.find('a')['href']
                
                # Multiple snippet selectors
                snippet = result.select_one('.VwiC3b, .lyLwlc, .ITZIwc, .MUxGbd')
                snippet_text = snippet.text if snippet else ""
                
                # Filter out invalid URLs
                if url.startswith('/search?') or url.startswith('/url?'):
                    continue
                    
                results.append({
                    "title": title.strip(),
                    "url": url,
                    "snippet": snippet_text.strip(),
                    "source": "google"
                })
                
            except Exception as e:
                logging.warning(f"Skipping result: {str(e)}")
                continue
                
        logging.info(f"Google search completed with {len(results)} results")
        return results
        
    except Exception as e:
        logging.error(f"Google search failed: {str(e)}")
        return []
    
def full_pipeline(query: str,  use_google: bool, use_wiki: bool):
    logging.info("\n" + "="*50)
    logging.info(f"Starting pipeline for query: '{query}'")
    try:
        results = combine_results(query, use_google, use_wiki)
        logging.info("Results combined, generating answer...")
        answer = generate_answer(query, results)
        logging.info("Pipeline completed successfully")
        return answer, json.dumps(results, indent=2)
    
    except Exception as e:
        logging.error(f"Pipeline failed: {str(e)}", exc_info=True)
        return f"Pipeline error: {str(e)}", json.dumps({"error": str(e)})
with gr.Blocks(title="Search Assistant") as demo:

    gr.Markdown("# 🔍 Smart Search Assistant")
    
    with gr.Row():
        query = gr.Textbox(label="Your Question", placeholder="How to learn car driving?")
        use_google = gr.Checkbox(label="Web Search", value=True)
        use_wiki = gr.Checkbox(label="Wikipedia", value=True)
    
    status = gr.Textbox(label="Search Status", interactive=False)
    submit_btn = gr.Button("Get Answer", variant="primary")
    
    with gr.Accordion("Advanced Results", open=False):
        json_output = gr.JSON()
    
    answer_output = gr.Markdown(label="Comprehensive Answer")
    
    submit_btn.click(
        fn=full_pipeline,
        inputs=[query, use_google, use_wiki],
        outputs=[answer_output, json_output],
        api_name="search"
    )
    
    # Live status updates
    query.change(lambda: "Ready for queries...", outputs=status)
    submit_btn.click(lambda: "Searching...", outputs=status)


if __name__ == "__main__":
    demo.launch(server_port=7860)
# how to learn car driving easily