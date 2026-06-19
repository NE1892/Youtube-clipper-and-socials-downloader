import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import requests

# --- Configuration ---
TARGET_URL = "https://example-ticketing-site.com/world-cup-match-1"
MAX_PRICE = 150  # Your budget limit
CHECK_INTERVAL = 30  # Time to wait between checks (in seconds)
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

def send_notification(ticket_info):
    """Sends an instant alert to a Telegram channel/chat."""
    message = f"🚨 Ticket Found! {ticket_info['name']} for ${ticket_info['price']}! Link: {TARGET_URL}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, json=payload)
    print("Notification sent!")

def monitor_tickets():
    # Set up a browser that runs in the background (headless)
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    driver = webdriver.Chrome(options=chrome_options)
    
    print("Starting ticket monitor...")
    
    try:
        while True:
            driver.get(TARGET_URL)
            time.sleep(3) # Wait for JavaScript elements to load
            
            # Find ticket elements on the page (e.g., HTML class names)
            try:
                ticket_elements = driver.find_elements(By.CLASS_NAME, "ticket-row")
                
                for element in ticket_elements:
                    # Extract the price text and convert it to an integer
                    price_text = element.find_element(By.CLASS_NAME, "ticket-price").text
                    price = int(price_text.replace("$", "").strip())
                    category_name = element.find_element(By.CLASS_NAME, "category-title").text
                    
                    print(f"Found: {category_name} - ${price}")
                    
                    # Check if the price fits the budget
                    if price <= MAX_PRICE:
                        send_notification({"name": category_name, "price": price})
                        
                        # Conceptual Step: Attempt to click "Add to Basket"
                        add_button = element.find_element(By.CLASS_NAME, "add-to-cart-btn")
                        add_button.click()
                        print("Attempted to add ticket to basket!")
                        return # Stop monitoring once found
                        
            except Exception as e:
                print("Could not find ticket elements. Site layout may have changed or queue is active.")
            
            # Wait before checking the website again
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        print("Monitoring stopped by user.")
    finally:
        driver.quit()

if __name__ == "__main__":
    monitor_tickets()