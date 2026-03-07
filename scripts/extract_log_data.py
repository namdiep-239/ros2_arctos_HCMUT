#!/usr/bin/env python3
"""
Script to extract data from ROS2 log files.
Extracts: timestamp (integer part), event type, joint/motor name, and values in rad and degrees.
"""

import re
import os
import csv
import math
from datetime import datetime


class LogDataExtractor:
    def __init__(self):
        # Regex patterns for different event types (excluding position_setting)
        # FIXED: Added support for negative numbers with [-+]?
        self.patterns = {
            'velocity_command': re.compile(
                r'\[(\d+\.[\d]{1,3})\d*\].*Sent velocity command ([-+]?[\d.]+) rad/s to joint (\w+)\..*'
            ),
            'position_command': re.compile(
                r'\[(\d+\.[\d]{1,3})\d*\].*Sent position command ([-+]?[\d.]+) rad to joint (\w+)\..*'
            ),
            'motor_update': re.compile(
                r'\[(\d+\.\d{1,3})\d*\].*Updated motor (\d+).*position: ([-+]?[\d.]+) (?:rad|degrees)'
            )
        }
    
    def extract_from_file(self, file_path):
        """Extract data from a single log file."""
        extracted_data = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or not '[' in line:
                        continue
                    
                    # Check each pattern
                    for event_type, pattern in self.patterns.items():
                        match = pattern.search(line)
                        if match:
                            data = self.parse_match(event_type, match, file_path, line_num)
                            if data:
                                extracted_data.append(data)
                            break
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
        
        return extracted_data
    
    def parse_match(self, event_type, match, file_path, line_num):
        """Parse regex match into structured data."""
        try:
            if event_type == 'velocity_command':
                timestamp, velocity, joint = match.groups()
                
                # Filter: only process C_joint
                if joint != 'C_joint':
                    return None
                    
                return {
                    'timestamp': float(timestamp),
                    'event': 'Sent velocity command',
                    'joint': joint,
                    'value_rad': float(velocity),
                    'value_deg': math.degrees(float(velocity)),
                    'unit': 'rad/s',
                    'file': os.path.basename(file_path),
                    'line': line_num,
                    'highlight': ''
                }
            
            elif event_type == 'position_command':
                timestamp, position, joint = match.groups()
                
                # Filter: only process C_joint
                if joint != 'C_joint':
                    return None
                    
                return {
                    'timestamp': float(timestamp),
                    'event': 'Sent position command',
                    'joint': joint,
                    'value_rad': float(position),
                    'value_deg': math.degrees(float(position)),
                    'unit': 'rad',
                    'file': os.path.basename(file_path),
                    'line': line_num,
                    'highlight': ''
                }
            
            elif event_type == 'motor_update':
                timestamp, motor_id, position = match.groups()
                joint_name = f'motor_{motor_id}'
                
                # Filter: only process motor_6, skip other motors
                if joint_name != 'motor_6':
                    return None
                    
                return {
                    'timestamp': float(timestamp),
                    'event': 'Updated motor position',
                    'joint': joint_name,
                    'value_rad': '',  # Leave empty - position is in degrees
                    'value_deg': float(position),  # Direct degree value
                    'unit': 'deg',
                    'file': os.path.basename(file_path),
                    'line': line_num,
                    'highlight': '***'
                }
                
        except (ValueError, IndexError) as e:
            print(f"Error parsing match in {file_path} line {line_num}: {e}")
            return None
    
    def extract_from_directory(self, directory_path):
        """Extract data from all log files in a directory."""
        all_data = []
        log_files = []
        
        # Find all log files
        for file_name in os.listdir(directory_path):
            if file_name.startswith('log_') and ('_' in file_name or file_name.endswith('.md')):
                file_path = os.path.join(directory_path, file_name)
                if os.path.isfile(file_path):
                    log_files.append(file_path)
        
        # Sort files for consistent processing order
        log_files.sort()
        
        print(f"Processing {len(log_files)} log files...")
        
        for file_path in log_files:
            print(f"Processing: {os.path.basename(file_path)}")
            file_data = self.extract_from_file(file_path)
            all_data.extend(file_data)
            print(f"  - Extracted {len(file_data)} events")
        
        return all_data
    
    def save_to_csv(self, data, output_file):
        """Save extracted data to CSV file."""
        if not data:
            print("No data to save.")
            return
        
        fieldnames = ['timestamp', 'event', 'joint', 'value_rad', 'value_deg', 'unit', 'file', 'line', 'highlight']
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            # Sort by timestamp
            sorted_data = sorted(data, key=lambda x: x['timestamp'])
            writer.writerows(sorted_data)
        
        print(f"Data saved to: {output_file}")
    
    def print_summary(self, data):
        """Print summary statistics of extracted data."""
        if not data:
            print("No data extracted.")
            return
        
        print("\n=== EXTRACTION SUMMARY ===")
        print(f"Total events extracted: {len(data)}")
        
        # Count by event type
        events_by_type = {}
        joints_by_type = {}
        files_processed = set()
        
        for item in data:
            event = item['event']
            joint = item['joint']
            file_name = item['file']
            
            events_by_type[event] = events_by_type.get(event, 0) + 1
            joints_by_type[joint] = joints_by_type.get(joint, 0) + 1
            files_processed.add(file_name)
        
        print(f"\nFiles processed: {', '.join(sorted(files_processed))}")
        
        print(f"\nEvents by type:")
        for event, count in sorted(events_by_type.items()):
            print(f"  {event}: {count}")
        
        print(f"\nJoints/Motors involved:")
        for joint, count in sorted(joints_by_type.items()):
            print(f"  {joint}: {count} events")
        
        # Time range
        timestamps = [item['timestamp'] for item in data]
        if timestamps:
            min_time = min(timestamps)
            max_time = max(timestamps)
            print(f"\nTime range: {min_time} - {max_time}")
            print(f"Duration: {max_time - min_time} seconds")


def main():
    """Main function to run the extraction."""
    # Configuration
    assets_dir = "/home/ngoccat/ros2_ws/src/ros2_arctos_HCMUT/assets"
    output_file = "/home/ngoccat/ros2_ws/src/ros2_arctos_HCMUT/extracted_log_data.csv"
    
    # Create extractor and process files
    extractor = LogDataExtractor()
    
    print("ROS2 Log Data Extractor")
    print("=====================")
    print(f"Source directory: {assets_dir}")
    print(f"Output file: {output_file}")
    
    # Extract data
    extracted_data = extractor.extract_from_directory(assets_dir)
    
    # Print summary
    extractor.print_summary(extracted_data)
    
    # Save to CSV
    if extracted_data:
        extractor.save_to_csv(extracted_data, output_file)
        print(f"\n✅ Extraction complete! Check {output_file}")
        
        # Show first few entries as example
        print(f"\nFirst 5 entries preview:")
        for i, item in enumerate(sorted(extracted_data, key=lambda x: x['timestamp'])[:5]):
            print(f"{i+1}. [{item['timestamp']}] {item['event']} -> {item['joint']}: "
                  f"{item['value_rad']:.3f} rad ({item['value_deg']:.2f}°)")
    else:
        print("\n❌ No data was extracted from the log files.")


if __name__ == "__main__":
    main()