import json
import random
import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
import argparse
import re
import os
import base64
from tqdm import tqdm
random.seed(42)

def answer_format(results):
    try:
        think = re.findall(r'<think>(.*?)</think>', results, re.DOTALL)
        answer = re.findall(r'<answer>(.*?)</answer>', results, re.DOTALL)
        error_type_list = re.findall(r'<error_type>(.*?)</error_type>', results, re.DOTALL)
        get_first = lambda l: l[0] if l else ""
        return {
            "output": results,
            "think": get_first(think),
            "answer": get_first(answer),
            "error_type_list": error_type_list
        }
    except Exception as e:
        return {
            "output": results,
            "think": "",
            "answer": "",
            "error_type_list": ""
        }


def get_gpt_response(image_path, prompt, api_model, api_key, base_url):
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    img_str = base64.b64encode(image_bytes).decode()
    try:
        client = OpenAI(
            api_key=api_key, 
            base_url=base_url
        )
        completion = client.chat.completions.create(
            model=api_model,
            messages=[
                {"role": "user", "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_str}"
                        }
                    },
                    {"type": "text", "text": prompt}
                ]}
            ],
            max_tokens=4096,
            temperature=0.0 
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] Failed to get response: {e}")
        return ""


def process_single_item(item, image_root, prompt, api_model):
    crop_path = os.path.join(image_root, item["crop_image"])
    response = get_gpt_response(crop_path, prompt + "\n" + item["pred"], api_model)
    item["response"] = answer_format(response)
    return item


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_model", type=str, required=True)
    parser.add_argument("--prompt_type", type=str, required=True)
    parser.add_argument("--max_workers", type=int, default=10)
    parser.add_argument("--api_key", type=int, default=10)
    parser.add_argument("--base_url", type=int, default=10)
    
    
    args = parser.parse_args()
    print("model: ", args.api_model)
    print("prompt type: ", args.prompt_type)
    print("max workers: ", args.max_workers)
    print("--------------------------------")

    with open(f"./utils/Prompt_{args.prompt_type}_think.txt", "r", encoding="utf-8") as f:
        prompt = f.read()
    with open("./DOCRcaseBench/benchmark_v1.json", "r", encoding="utf-8") as f:
        data = json.load(f)
  
    image_root = "./DOCRcaseBench/image"
    save_root = "./results"

    final_data = []
    

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:

        future_to_item = {
            executor.submit(process_single_item, item, image_root, prompt, args.api_model,args.api_key,args.base_url): item 
            for item in data
        }
        

        for future in tqdm(as_completed(future_to_item), total=len(data), desc="Processing items"):
            try:
                result = future.result()
                final_data.append(result)
            except Exception as e:
                print(f"[ERROR] Task failed: {e}")

                original_item = future_to_item[future]
                original_item["output"] = answer_format("")
                final_data.append(original_item)

    with open(os.path.join(save_root, f"{args.api_model}_{args.prompt_type}CoT_test_results.json"), "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)