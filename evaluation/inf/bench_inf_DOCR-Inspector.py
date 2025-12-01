import sys
# print(sys.path)
import argparse
from transformers import AutoProcessor
from PIL import Image
from vllm import LLM, SamplingParams
import glob
import os
import json
import torch
from qwen_vl_utils import process_vision_info
from tqdm import tqdm
import re
import gc


Image.MAX_IMAGE_PIXELS = None

def process_input(image_path, prompt, processor):
    try:
        contents = [
            {
                "type": "image", 
                "image": Image.open(image_path).convert('RGB'),
                "min_pixels": 224 * 224, 
                "max_pixels": 1280 * 28 * 28,
            }
        ]
        messages = [
            {
                "role": "user",
                "content": [
                    *contents,
                    {"type": "text", "text": prompt},
                ],
            }]
        
        prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        img_data, _ = process_vision_info(messages)
        
        return {
            "prompt": prompt,
            "multi_modal_data": {"image": img_data},
        }
    except Exception as e:
        print(f"Error processing image {image_path}: {str(e)}")
        return None

def inference(image_paths, prompts, llm, processor):
    sampling_params = SamplingParams(temperature=0.0, max_tokens=32768)
    inputs = []

    for path, prompt in tqdm(zip(image_paths, prompts), desc="Processing Images"):
        processed_input = process_input(path, prompt, processor)
        if processed_input is not None:
            inputs.append(processed_input)

    outputs = llm.generate(inputs, sampling_params=sampling_params)

    results  = [ o.outputs[0].text if o.outputs else "" for o in outputs]
    return results

def answer_format(results):
    try:
        category = re.findall(r'<category>(.*?)</category>', results, re.DOTALL)
        think = re.findall(r'<think>(.*?)</think>', results, re.DOTALL)
        answer = re.findall(r'<answer>(.*?)</answer>', results, re.DOTALL)
        error_type_list = re.findall(r'<error_type>(.*?)</error_type>', results, re.DOTALL)
        get_first = lambda l: l[0] if l else ""
        return {
            "output": results,
            "think": get_first(think),
            "category": get_first(category),
            "answer": get_first(answer),
            "error_type_list": error_type_list
        }
    except Exception as e:
        return {
            "output": results,
            "think": "",
            "category": "",
            "answer": "",
            "error_type_list": ""
        }

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--model_type', type=str, required=True)
    parser.add_argument('--model_path', type=str, required=True)
    args = parser.parse_args()
    model_type = args.model_type
    model_path = args.model_path
    
    PROMPT = "Analyze the quality of OCR results for the given image."
    
    print(f"Loading model: {model_path}")

    print("Initializing processor and model...")
    try:
        processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
        llm = LLM(
            model=model_path,
            tensor_parallel_size=torch.cuda.device_count(),
            max_model_len=32768,
            trust_remote_code=True,
        )
        print("Model and processor initialized successfully.")
        
        with open("./DOCRcaseBench/benchmark_v1.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        final_data = []
        image_paths = []
        prompts = []
        
        for item in data:
            image_paths.append(os.path.join("./DOCRcaseBench/image", item["crop_image"]))
            prompt_text = f"<image>\n{PROMPT}\n<ocr_content>\n{item['pred']}\n</ocr_content>"
            prompts.append(prompt_text)
            
        results = inference(image_paths, prompts, llm, processor)
        
        for result, item in zip(results, data):
            formatted_result = answer_format(result)
            item["output"] = formatted_result
            final_data.append(item)

        print(f"Processed {len(final_data)} items")
            
        output_dir = "./results"
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, f"{model_type}_test_results.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=4)
            
        print(f"Completed processing for model: {model_type}")
        print(f"Results saved to: {output_file}")
        
    except Exception as e:
        print(f"Error processing model {model_type}: {str(e)}")
        return
    
    print(f"Model {model_type} processed successfully!")

if __name__ == "__main__": 
    main()