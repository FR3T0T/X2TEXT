import tweepy
import json
import time
import os
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("twitter_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()

class TwitterScraper:
    def __init__(self, credentials_file="twitter_credentials.json"):
        """Initialize the Twitter scraper with API credentials"""
        # Check if credentials file exists, if not create it first
        if not os.path.exists(credentials_file):
            self._create_sample_credentials(credentials_file)
            logger.info(f"Please fill in your API credentials in {credentials_file} and run the program again.")
            exit(1)
            
        self.credentials = self._load_credentials(credentials_file)
        self.client = self._authenticate()
        self.data_dir = "twitter_data"
        os.makedirs(self.data_dir, exist_ok=True)
    
    def _create_sample_credentials(self, file_path):
        """Create a sample credentials file"""
        sample = {
            "consumer_key": "YOUR_CONSUMER_KEY",
            "consumer_secret": "YOUR_CONSUMER_SECRET",
            "access_token": "YOUR_ACCESS_TOKEN",
            "access_token_secret": "YOUR_ACCESS_TOKEN_SECRET",
            "bearer_token": "YOUR_BEARER_TOKEN"
        }
        with open(file_path, 'w') as f:
            json.dump(sample, f, indent=4)
        logger.info(f"Sample credentials file created at {file_path}")
        
    def _load_credentials(self, file_path):
        """Load Twitter API credentials from JSON file"""
        try:
            with open(file_path, 'r') as f:
                credentials = json.load(f)
                
            # Check if credentials have been updated from defaults
            if credentials["consumer_key"] == "YOUR_CONSUMER_KEY":
                logger.error(f"API credentials in {file_path} have not been updated. Please add your actual API credentials.")
                exit(1)
                
            return credentials
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in credentials file: {file_path}")
            self._create_sample_credentials(file_path)
            logger.info(f"Please fill in your API credentials in {file_path} and run the program again.")
            exit(1)
        except Exception as e:
            logger.error(f"Error reading credentials: {e}")
            exit(1)
    
    def _authenticate(self):
        """Authenticate with Twitter API"""
        try:
            client = tweepy.Client(
                bearer_token=self.credentials["bearer_token"],
                consumer_key=self.credentials["consumer_key"],
                consumer_secret=self.credentials["consumer_secret"],
                access_token=self.credentials["access_token"],
                access_token_secret=self.credentials["access_token_secret"],
                wait_on_rate_limit=True
            )
            logger.info("Successfully authenticated with Twitter API")
            return client
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            exit(1)
    
    def get_user_id(self, username):
        """Get user ID from username"""
        try:
            user = self.client.get_user(username=username)
            if user.data:
                return user.data.id
            else:
                logger.error(f"User not found: {username}")
                return None
        except Exception as e:
            logger.error(f"Error getting user ID for {username}: {e}")
            return None
    
    def get_user_tweets(self, user_id, max_tweets=100):
        """Get tweets from a specific user"""
        tweet_fields = ['created_at', 'public_metrics', 'source', 'lang', 'context_annotations', 'entities']
        user_fields = ['name', 'username', 'description', 'public_metrics', 'verified', 'profile_image_url']
        expansions = ['author_id', 'referenced_tweets.id', 'attachments.media_keys']
        media_fields = ['type', 'url', 'alt_text', 'public_metrics']
        
        all_tweets = []
        pagination_token = None
        
        # Paginate through results
        while True:
            try:
                tweets = self.client.get_users_tweets(
                    id=user_id,
                    tweet_fields=tweet_fields,
                    user_fields=user_fields,
                    expansions=expansions,
                    media_fields=media_fields,
                    max_results=100,  # API max per request
                    pagination_token=pagination_token
                )
                
                # Break if no tweets returned
                if not tweets.data:
                    break
                    
                # Process tweets
                all_tweets.extend(self._process_tweets(tweets))
                
                # Check if we've reached our desired max
                if len(all_tweets) >= max_tweets:
                    all_tweets = all_tweets[:max_tweets]
                    break
                
                # Get next pagination token
                if 'next_token' in tweets.meta:
                    pagination_token = tweets.meta['next_token']
                else:
                    break
                    
                # Small delay to be respectful of API limits
                time.sleep(1)
                
            except tweepy.TooManyRequests:
                logger.warning("Rate limit hit. Waiting 15 minutes before retrying...")
                time.sleep(15 * 60)
            except Exception as e:
                logger.error(f"Error fetching tweets: {e}")
                break
                
        return all_tweets
    
    def _process_tweets(self, tweets_response):
        """Process tweets and extract relevant information"""
        processed_tweets = []
        
        if not tweets_response.data:
            return processed_tweets
            
        # Create lookup dictionaries for included data
        users = {}
        if 'users' in tweets_response.includes:
            users = {user.id: user for user in tweets_response.includes['users']}
            
        media = {}
        if 'media' in tweets_response.includes:
            media = {m.media_key: m for m in tweets_response.includes['media']}
            
        tweets_lookup = {}
        if 'tweets' in tweets_response.includes:
            tweets_lookup = {t.id: t for t in tweets_response.includes['tweets']}
        
        # Process each tweet
        for tweet in tweets_response.data:
            # Get author info
            author = users.get(tweet.author_id, None)
            author_info = None
            
            if author:
                author_info = {
                    'id': author.id,
                    'name': author.name,
                    'username': author.username,
                    'description': author.description,
                    'followers_count': author.public_metrics['followers_count'],
                    'following_count': author.public_metrics['following_count'],
                    'tweet_count': author.public_metrics['tweet_count'],
                    'verified': getattr(author, 'verified', False),
                    'profile_image_url': getattr(author, 'profile_image_url', None)
                }
            
            # Process media attachments
            media_items = []
            if hasattr(tweet, 'attachments') and hasattr(tweet.attachments, 'media_keys'):
                for media_key in tweet.attachments.media_keys:
                    if media_key in media:
                        m = media[media_key]
                        media_item = {
                            'type': m.type,
                            'media_key': media_key,
                            'url': getattr(m, 'url', None),
                            'alt_text': getattr(m, 'alt_text', None)
                        }
                        
                        if hasattr(m, 'public_metrics'):
                            media_item['metrics'] = m.public_metrics
                            
                        media_items.append(media_item)
            
            # Process referenced tweets (retweets, quotes, replies)
            referenced_tweets = []
            if hasattr(tweet, 'referenced_tweets') and tweet.referenced_tweets:
                for ref in tweet.referenced_tweets:
                    ref_data = {
                        'type': ref.type,
                        'id': ref.id
                    }
                    
                    # If we have the referenced tweet in our includes
                    if ref.id in tweets_lookup:
                        ref_tweet = tweets_lookup[ref.id]
                        ref_data['text'] = ref_tweet.text
                        ref_data['created_at'] = ref_tweet.created_at.isoformat()
                        if hasattr(ref_tweet, 'public_metrics'):
                            ref_data['public_metrics'] = ref_tweet.public_metrics
                            
                    referenced_tweets.append(ref_data)
            
            # Extract hashtags, mentions, and URLs
            entities = {
                'hashtags': [],
                'mentions': [],
                'urls': []
            }
            
            if hasattr(tweet, 'entities'):
                if hasattr(tweet.entities, 'hashtags') and tweet.entities.hashtags:
                    entities['hashtags'] = [tag['tag'] for tag in tweet.entities.hashtags]
                
                if hasattr(tweet.entities, 'mentions') and tweet.entities.mentions:
                    entities['mentions'] = [
                        {'username': mention['username'], 'id': mention['id']} 
                        for mention in tweet.entities.mentions
                    ]
                
                if hasattr(tweet.entities, 'urls') and tweet.entities.urls:
                    entities['urls'] = [
                        {'url': url['url'], 'expanded_url': url['expanded_url']} 
                        for url in tweet.entities.urls
                    ]
            
            # Create final tweet object
            tweet_obj = {
                'id': tweet.id,
                'text': tweet.text,
                'created_at': tweet.created_at.isoformat(),
                'lang': getattr(tweet, 'lang', None),
                'source': getattr(tweet, 'source', None),
                'public_metrics': getattr(tweet, 'public_metrics', None),
                'author': author_info,
                'media': media_items if media_items else None,
                'referenced_tweets': referenced_tweets if referenced_tweets else None,
                'entities': entities
            }
            
            processed_tweets.append(tweet_obj)
            
        return processed_tweets
    
    def follow_users(self, usernames, tweets_per_user=100):
        """Follow multiple Twitter users and collect their tweets"""
        all_data = {}
        
        for username in usernames:
            logger.info(f"Processing tweets for user: {username}")
            user_id = self.get_user_id(username)
            
            if not user_id:
                logger.warning(f"Could not find user ID for {username}, skipping")
                continue
                
            tweets = self.get_user_tweets(user_id, max_tweets=tweets_per_user)
            logger.info(f"Retrieved {len(tweets)} tweets for {username}")
            
            if tweets:
                all_data[username] = tweets
                # Save data for this user
                self._save_user_data(username, tweets)
                
        return all_data
    
    def _save_user_data(self, username, tweets):
        """Save user tweets to a JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self.data_dir, f"{username}_{timestamp}.json")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(tweets, f, ensure_ascii=False, indent=4)
            
        logger.info(f"Saved {len(tweets)} tweets for {username} to {filename}")

def main():
    # List of usernames to follow
    usernames = [
        "elonmusk",
        "WhiteHouse",
        "realDonaldTrump",
        "POTUS",
        "SecDef",
        "SecRubio"
    ]
    
    # Create scraper instance
    scraper = TwitterScraper()
    
    # Collect tweets
    data = scraper.follow_users(usernames, tweets_per_user=50)
    
    # Save all data to a combined file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    combined_file = os.path.join(scraper.data_dir, f"all_tweets_{timestamp}.json")
    
    with open(combined_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    logger.info(f"Saved combined data to {combined_file}")
    logger.info("Execution complete")

if __name__ == "__main__":
    main()