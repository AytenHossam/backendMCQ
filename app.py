import requests
import random
import re
import langdetect
import json
from flask import Flask, request, jsonify
from flask_cors import CORS  

app = Flask(__name__)
CORS(app)  

GROQ_API_KEY = "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"

def detect_language(text):
    """Detects the language of the input text."""
    try:
        lang = langdetect.detect(text)
        return lang
    except:
        return "unknown"
    

def clean_choice(choice):
    """Removes extra numbering and trims whitespace from answer choices."""
    return re.sub(r"^\d+\.\s*", "", choice).strip()


def split_distractors(distractors_text):
    """Ensures distractors are properly split into individual answers."""
    # Ensure that we split by commas or other delimiters, and clean extra spaces
    distractors = re.split(r"[،,]\s*", distractors_text)  # Split by commas and spaces or Arabic comma
    return [d.strip() for d in distractors if d.strip()]  # Remove empty elements


def assign_choice_labels(choices, language):
    """Assigns appropriate labels for multiple languages."""
    language_labels = {
        "en": ["A", "B", "C", "D"],
        "ar": ["أ", "ب", "ج", "د"],
        "es": ["A", "B", "C", "D"],  # Spanish
        "fr": ["A", "B", "C", "D"],  # French
        "de": ["A", "B", "C", "D"],  # German
        "it": ["A", "B", "C", "D"],  # Italian
    }
    
    labels = language_labels.get(language, ["A", "B", "C", "D"])  # Default to English labels
    return {labels[i]: choices[i] for i in range(len(choices))}

def is_invalid_question(question):
    """Detects if a question is personal, unclear, or nonsensical using the Groq model."""
    
    prompt = f"""
    The question is considered invalid if:
    1. It is personal, like asking about one's name, location, etc. (e.g., "What’s my name?")
    2. It is unclear or ambiguous, such as "What is this?", "Tell me more", or "Explain this."
    3. It is a joke or has no meaningful context, such as "Why did the chicken cross the road?" or "Tell me a joke."
    4. Any nonsense that doesn’t have an answer.
    5.It's in complete in any part fo the question example:" Where is ?" or "old are " or "Where is located?"
    6.A rhetorical question used to express confusion or unclear situation.
    7.If the question is not understod by a human in case of context.
    
    Classify the following question as:
    - True → if it matches any of the invalid types above.
    - False → if it is a valid question that can be used for a quiz.

    Question: "{question}"
    Response:"""
    
    api_url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0,
        "max_tokens": 10
    }

    response = requests.post(api_url, json=payload, headers=headers)

    if response.status_code == 200:
        try:
            content = response.json()["choices"][0]["message"]["content"].strip().lower()
            return "true" in content
        except Exception as e:
            print(f"⚠️ Parsing error in is_invalid_question: {e}")
            return False

    print(f"⚠️ Request error in is_invalid_question: {response.status_code}")
    return False


def regenerate_distractors(question, correct_answer, language, existing_distractors):
    """Use LLM to generate more distractors based on correct answer and existing distractors."""
    max_attempts = 3
    needed = 3 - len(existing_distractors)
    generated = []

    for attempt in range(max_attempts):
        if len(existing_distractors) + len(generated) >= 3:
            break  # Exit early if we have enough

        prompt = f"""
        You're a smart quiz assistant.

        The question is: "{question}"
        The correct answer is: "{correct_answer}"
        Current distractors are: {', '.join(existing_distractors + generated)}.

        Please generate {3 - (len(existing_distractors) + len(generated))} **additional plausible distractors**.
        Do not repeat existing distractors or the correct answer.
        The plausible distractors should be short and direct. Do not include explanations or details.
        Dont make the plausible distractors start with the same 2 words.
        The plausible distractors should be maximum of 10 words.
        
        Return them in this format:
        Distractors: <d1>, <d2>
        """

        data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 100
        }

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=data, headers=headers)

        if response.status_code == 200:
            try:
                content = response.json()["choices"][0]["message"]["content"].strip()
                new_distractors = split_distractors(content.replace("Distractors:", "").strip())
                filtered = [d for d in new_distractors if d not in existing_distractors and d not in generated and d != correct_answer]
                generated.extend(filtered)
            except Exception as e:
                print(f"⚠️ Parsing error on attempt {attempt + 1}: {e}")
                continue
        else:
            print(f"⚠️ API error on attempt {attempt + 1}: {response.status_code} - {response.text}")
            continue

    return generated[:needed]  # Return only the number we needed


def regenerate_correct_answer(question, language):
    """Regenerates the correct answer for the question using a different LLM."""
    max_attempts = 3
    correct_answer = None

    for attempt in range(max_attempts):
        prompt = f"""
        You are a smart quiz assistant.
        Given the question: "{question}", generate the **correct answer**.
        
        Please make sure to generate only one correct answer with one correct information.
        If the question contains the word 'x', do not generate the correct answer as 'x is ...' or any variation of this phrase. The correct answer should not explicitly use the phrase 'x is' or something that immediately associates the correct answer with the word 'x' in such a straightforward way.
        The correct answer should be factual and directly related to the question.
        The correct answer should be short and direct. 
        Do not include explanations or details in the correct answer.
        The correct answer should be maximum of 10 words.

        Avoid ambiguity.

        Return only the correct answer, no distractors.
        """

        data = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",  # Example of a multilingual model
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 100
        }

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=data, headers=headers)

        if response.status_code == 200:
            try:
                content = response.json()["choices"][0]["message"]["content"].strip()
                if content:
                    correct_answer = clean_choice(content)
                    break  # If correct answer is generated, break out of the loop
            except Exception as e:
                print(f"⚠️ Parsing error on attempt {attempt + 1}: {e}")
                continue
        else:
            print(f"⚠️ API error on attempt {attempt + 1}: {response.status_code} - {response.text}")
            continue

    return correct_answer

def generate_multiple_choice(question):
    """Generates a multiple-choice question with 1 correct answer and 3 distractors using Groq API."""
    # Check if the question is invalid first
    if is_invalid_question(question):
        return json.dumps({"error": "⚠️ Invalid question detected."})
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    # Detect language of the question
    language = detect_language(question)
    if language == "unknown":
        return json.dumps({"error": "⚠️ Unsupported language detected."})

    prompt = f"""
    You are a multilingual multiple-choice question generator.
    Given the question: "{question}", generate:
    1. The correct answer
    2. Three incorrect but plausible distractors.

    Make sure to only generate one correct answer.
    If the question contains the word 'x', do not generate the correct answer as 'x is ...' or any variation of this phrase. The correct answer should not explicitly use the phrase 'x is' or something that immediately associates the correct answer with the word 'x' in such a straightforward way.
    The distractors should be very closely related to the correct answer — similar in meaning,
    structure, or concept — to increase difficulty and make students carefully consider their choice. 
    Avoid obvious or unrelated distractors but do not make it extremely difficult; aim for medium to difficult level.
    Return the response in the same language as the question.
    The correct answer should be short and direct. Do not include explanations or details in the correct answer.
    The plausible distractors should be short and direct. Do not include explanations or details in the plausible distractors.
    Dont make the plausible distractors start with the same 2 words.
    The correct answer and plausible distractors should be maximum of 10 words.

    Format response as:
    Question: <question>
    Correct Answer: <correct answer>
    Distractors: <distractor 1>, <distractor 2>, <distractor 3>
    """

    data = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",  # Example of a multilingual model
        "messages": [
            {"role": "system", "content": "You generate multiple-choice quiz questions in plain text format, always using the same language as the question."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 200
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        result = response.json()

        try:
            generated_text = result["choices"][0]["message"]["content"].strip()
            if not generated_text:
                return json.dumps({"error": "⚠️ API returned an empty response."})

            # Extract and parse response
            lines = generated_text.split("\n")
            question_text = lines[0].replace("Question: ", "").strip()
            correct_answer = ""
            distractors = []

            for line in lines:
                if line.startswith("Question:"):
                   question_text = line.replace("Question:", "").strip()
                elif line.startswith("Correct Answer:"):
                   correct_answer = clean_choice(line.replace("Correct Answer:", "").strip())
                elif line.startswith("Distractors:"):
                   distractors_line = line.replace("Distractors:", "").strip()
                   distractors = split_distractors(distractors_line)

            # If no correct answer was generated, attempt to regenerate it
            if not correct_answer:
                correct_answer = regenerate_correct_answer(question_text, language)
                if not correct_answer:
                    return json.dumps({"error": "⚠️ Failed to generate a correct answer."})

            # Handle any distracting entries that might be too long or incorrect
            distractors = [clean_choice(d) for d in distractors if "Correct Answer:" not in d]

            # Ensure there are 3 distractors
            if len(distractors) != 3:
                additional = regenerate_distractors(question_text, correct_answer, language, distractors)
                distractors += additional
                distractors = list(set(distractors))  # Remove duplicates
                distractors = [d for d in distractors if d != correct_answer]
                distractors = distractors[:3]  # Keep only 3
                
                if len(distractors) < 3:
                    return json.dumps({"error": "⚠️ Unable to generate enough distractors even after fallback."})

            # Shuffle answer choices
            choices = [correct_answer] + distractors
            random.shuffle(choices)

            # Assign labels for multiple languages
            formatted_choices = assign_choice_labels(choices, language)
            correct_label = next(label for label, choice in formatted_choices.items() if choice == correct_answer)

            return json.dumps({
                "question": question_text,
                "choices": formatted_choices,
                "correct_label": correct_label
            })
        except Exception as e:
            return json.dumps({"error": f"⚠️ Failed to parse API response: {e}"})
    
    return json.dumps({"error": f"⚠️ API request failed: {response.text}"})



@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json()
    question = data.get("question", "")
    if not question:
        return jsonify({"error": "⚠️ Please provide a 'question' field in the request body."}), 400
    
    result = generate_multiple_choice(question)
    return jsonify(json.loads(result))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)
