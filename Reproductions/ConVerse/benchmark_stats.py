#!/usr/bin/env python3
"""
ConVerse Benchmark Statistics Module

Provides comprehensive statistics and analysis of the benchmark including:
- Use case overview and properties
- Attack type distribution and complexity
- Persona diversity and coverage
- Data richness metrics
- Benchmark complexity analysis
"""

import json
import os
import sys
from typing import Dict, List, Any, Set
from dataclasses import dataclass
from collections import defaultdict, Counter
import argparse

# Add parent directory to path for imports
current = os.path.dirname(os.path.realpath(__file__))
sys.path.append(current)

from use_cases.config import registry, UseCaseFileResolver


@dataclass
class BenchmarkStats:
    """Container for all benchmark statistics"""
    use_case_stats: Dict[str, Any]
    attack_stats: Dict[str, Any]
    persona_stats: Dict[str, Any]
    data_richness: Dict[str, Any]
    complexity_metrics: Dict[str, Any]
    overall_summary: Dict[str, Any]


class BenchmarkAnalyzer:
    """Analyzes the ConVerse Benchmark for comprehensive statistics"""
    
    def __init__(self, base_path: str = ""):
        self.base_path = base_path
        self.file_resolver = UseCaseFileResolver(base_path)
        self.registry = registry
        
    def analyze_benchmark(self) -> BenchmarkStats:
        """Perform comprehensive benchmark analysis"""
        print("🔍 Analyzing ConVerse Benchmark...")
        
        use_case_stats = self._analyze_use_cases()
        attack_stats = self._analyze_attacks()
        persona_stats = self._analyze_personas()
        data_richness = self._analyze_data_richness()
        complexity_metrics = self._calculate_complexity_metrics()
        overall_summary = self._generate_overall_summary(
            use_case_stats, attack_stats, persona_stats, data_richness, complexity_metrics
        )
        
        return BenchmarkStats(
            use_case_stats=use_case_stats,
            attack_stats=attack_stats,
            persona_stats=persona_stats,
            data_richness=data_richness,
            complexity_metrics=complexity_metrics,
            overall_summary=overall_summary
        )
    
    def _analyze_use_cases(self) -> Dict[str, Any]:
        """Analyze use case properties and coverage"""
        use_cases = self.registry.list_use_cases()
        stats = {
            "total_count": len(use_cases),
            "use_case_details": {},
            "domains": set(),
            "total_personas": 0,
            "persona_distribution": {},
            "agent_roles": {}
        }
        
        for use_case_name in use_cases:
            config = self.registry.get_use_case(use_case_name)
            if not config:
                continue
                
            # Extract domain from use case name or role
            domain = use_case_name.replace('_', ' ').title()
            stats["domains"].add(domain)
            
            # Count options if available
            options_file = self.file_resolver.get_options_file(config)
            options_count = 0
            if os.path.exists(options_file):
                try:
                    with open(options_file, 'r') as f:
                        options_count = len(f.readlines())
                except:
                    options_count = 0
            
            stats["use_case_details"][use_case_name] = {
                "description": config.description,
                "domain": domain,
                "external_agent_role": config.external_agent_role,
                "supported_personas": config.supported_personas,
                "persona_count": len(config.supported_personas),
                "options_count": options_count,
                "resource_folder": config.resource_folder
            }
            
            stats["persona_distribution"][use_case_name] = len(config.supported_personas)
            stats["agent_roles"][use_case_name] = config.external_agent_role
            stats["total_personas"] += len(config.supported_personas)
        
        stats["domains"] = list(stats["domains"])
        stats["avg_personas_per_use_case"] = stats["total_personas"] / len(use_cases) if use_cases else 0
        
        return stats
    
    def _analyze_attacks(self) -> Dict[str, Any]:
        """Analyze attack types, categories, and properties"""
        stats = {
            "security_attacks": self._analyze_security_attacks(),
            "privacy_attacks": self._analyze_privacy_attacks(),
            "total_attacks": 0,
            "attack_distribution": {},
            "complexity_analysis": {}
        }
        
        # Calculate totals
        stats["total_attacks"] = (
            stats["security_attacks"]["total_count"] + 
            stats["privacy_attacks"]["total_count"]
        )
        
        # Distribution analysis
        for use_case_name in self.registry.list_use_cases():
            config = self.registry.get_use_case(use_case_name)
            if not config:
                continue
                
            use_case_attacks = {"security": 0, "privacy": 0}
            
            for persona_id in config.supported_personas:
                # Count security attacks
                sec_file = self.file_resolver.get_security_attacks_file(config, persona_id)
                if os.path.exists(sec_file):
                    use_case_attacks["security"] += self._count_attacks_in_file(sec_file, "security_attacks")
                
                # Count privacy attacks  
                priv_file = self.file_resolver.get_privacy_attacks_file(config, persona_id)
                if os.path.exists(priv_file):
                    use_case_attacks["privacy"] += self._count_attacks_in_file(priv_file, "categories")
            
            stats["attack_distribution"][use_case_name] = use_case_attacks
        
        return stats
    
    def _analyze_security_attacks(self) -> Dict[str, Any]:
        """Analyze security attack categories and properties"""
        stats = {
            "total_count": 0,
            "categories": set(),
            "responsibility_flags": Counter(),
            "harm_levels": Counter(),
            "detection_difficulty": Counter(),
            "by_use_case": {}
        }
        
        for use_case_name in self.registry.list_use_cases():
            config = self.registry.get_use_case(use_case_name)
            if not config:
                continue
                
            use_case_security = {
                "total": 0,
                "categories": set(),
                "responsibility_flags": Counter(),
                "harm_levels": Counter()
            }
            
            for persona_id in config.supported_personas:
                sec_file = self.file_resolver.get_security_attacks_file(config, persona_id)
                if os.path.exists(sec_file):
                    try:
                        with open(sec_file, 'r') as f:
                            data = json.load(f)
                            security_attacks = data.get("security_attacks", {})
                            
                            for category, attacks in security_attacks.items():
                                stats["categories"].add(category)
                                use_case_security["categories"].add(category)
                                
                                for attack_key, attack_data in attacks.items():
                                    stats["total_count"] += 1
                                    use_case_security["total"] += 1
                                    
                                    # Analyze properties
                                    if "responsibility_flag" in attack_data:
                                        flag = attack_data["responsibility_flag"]
                                        stats["responsibility_flags"][flag] += 1
                                        use_case_security["responsibility_flags"][flag] += 1
                                    
                                    if "harm_potential" in attack_data:
                                        harm = attack_data["harm_potential"]
                                        stats["harm_levels"][harm] += 1
                                        use_case_security["harm_levels"][harm] += 1
                                    
                                    if "detection_difficulty" in attack_data:
                                        difficulty = attack_data["detection_difficulty"]
                                        stats["detection_difficulty"][difficulty] += 1
                    except Exception as e:
                        print(f"Warning: Could not analyze {sec_file}: {e}")
            
            # Convert sets to lists for JSON serialization
            use_case_security["categories"] = list(use_case_security["categories"])
            stats["by_use_case"][use_case_name] = use_case_security
        
        stats["categories"] = list(stats["categories"])
        return stats
    
    def _analyze_privacy_attacks(self) -> Dict[str, Any]:
        """Analyze privacy attack categories and data types"""
        stats = {
            "total_count": 0,
            "data_categories": set(),
            "information_types": set(),
            "privacy_levels": Counter(),
            "leak_types": Counter(),
            "by_use_case": {}
        }
        
        for use_case_name in self.registry.list_use_cases():
            config = self.registry.get_use_case(use_case_name)
            if not config:
                continue
                
            use_case_privacy = {
                "total": 0,
                "data_categories": set(),
                "information_types": set(),
                "privacy_levels": Counter()
            }
            
            for persona_id in config.supported_personas:
                priv_file = self.file_resolver.get_privacy_attacks_file(config, persona_id)
                if os.path.exists(priv_file):
                    try:
                        with open(priv_file, 'r') as f:
                            data = json.load(f)
                            categories = data.get("categories", {})
                            
                            for category_name, category_data in categories.items():
                                stats["data_categories"].add(category_name)
                                use_case_privacy["data_categories"].add(category_name)
                                
                                # Check if category has items (direct structure)
                                if "items" in category_data:
                                    for item in category_data["items"]:
                                        stats["total_count"] += 1
                                        use_case_privacy["total"] += 1
                                        
                                        # Extract information types
                                        if "data_item" in item:
                                            info_type = item["data_item"]
                                            stats["information_types"].add(info_type)
                                            use_case_privacy["information_types"].add(info_type)
                                        
                                        # Analyze privacy levels
                                        if "privacy_level" in item:
                                            level = item["privacy_level"]
                                            stats["privacy_levels"][level] += 1
                                            use_case_privacy["privacy_levels"][level] += 1
                                        
                                        # Analyze leak types
                                        if "extraction_snippets" in item:
                                            stats["leak_types"]["extraction_based"] += 1
                                        if "acceptable_abstraction" in item:
                                            stats["leak_types"]["abstraction_based"] += 1
                                
                                # Check if category has attacks (alternative structure)
                                elif "attacks" in category_data:
                                    for attack_key, attack_data in category_data["attacks"].items():
                                        stats["total_count"] += 1
                                        use_case_privacy["total"] += 1
                                        
                                        # Extract information types
                                        if "data_item" in attack_data:
                                            info_type = attack_data["data_item"]
                                            stats["information_types"].add(info_type)
                                            use_case_privacy["information_types"].add(info_type)
                                        
                                        # Analyze leak types
                                        if "extraction_snippets" in attack_data:
                                            stats["leak_types"]["extraction_based"] += 1
                                        if "acceptable_abstraction" in attack_data:
                                            stats["leak_types"]["abstraction_based"] += 1
                    except Exception as e:
                        print(f"Warning: Could not analyze {priv_file}: {e}")
            
            # Convert sets to lists for JSON serialization
            use_case_privacy["data_categories"] = list(use_case_privacy["data_categories"])
            use_case_privacy["information_types"] = list(use_case_privacy["information_types"])
            stats["by_use_case"][use_case_name] = use_case_privacy
        
        stats["data_categories"] = list(stats["data_categories"])
        stats["information_types"] = list(stats["information_types"])
        return stats
    
    def _analyze_personas(self) -> Dict[str, Any]:
        """Analyze persona diversity and characteristics"""
        stats = {
            "total_unique_personas": set(),
            "persona_coverage": {},
            "demographic_diversity": {},
            "preference_patterns": {}
        }
        
        for use_case_name in self.registry.list_use_cases():
            config = self.registry.get_use_case(use_case_name)
            if not config:
                continue
                
            for persona_id in config.supported_personas:
                stats["total_unique_personas"].add(persona_id)
                
                # Analyze persona from security attacks file (has persona info)
                sec_file = self.file_resolver.get_security_attacks_file(config, persona_id)
                if os.path.exists(sec_file):
                    try:
                        with open(sec_file, 'r') as f:
                            data = json.load(f)
                            persona_info = data.get("persona", {})
                            
                            persona_key = f"{use_case_name}_persona_{persona_id}"
                            stats["persona_coverage"][persona_key] = {
                                "name": persona_info.get("name", f"Persona {persona_id}"),
                                "profile_summary": persona_info.get("profile_summary", ""),
                                "use_case": use_case_name,
                                "persona_id": persona_id
                            }
                    except Exception as e:
                        print(f"Warning: Could not analyze persona in {sec_file}: {e}")
                
                # Analyze ratings/preferences
                ratings_file = self.file_resolver.get_ratings_file(config, persona_id)
                if os.path.exists(ratings_file):
                    try:
                        with open(ratings_file, 'r') as f:
                            ratings_data = json.load(f)
                            persona_key = f"{use_case_name}_persona_{persona_id}"
                            stats["preference_patterns"][persona_key] = {
                                "total_preferences": len(ratings_data),
                                "rating_categories": list(ratings_data.keys()) if isinstance(ratings_data, dict) else []
                            }
                    except Exception as e:
                        print(f"Warning: Could not analyze ratings in {ratings_file}: {e}")
        
        stats["total_unique_personas"] = len(stats["total_unique_personas"])
        return stats
    
    def _analyze_data_richness(self) -> Dict[str, Any]:
        """Analyze the richness and variety of benchmark data"""
        stats = {
            "file_counts": {},
            "data_volume": {},
            "option_diversity": {},
            "environment_complexity": {}
        }
        
        for use_case_name in self.registry.list_use_cases():
            config = self.registry.get_use_case(use_case_name)
            if not config:
                continue
                
            use_case_richness = {
                "total_files": 0,
                "security_attack_files": 0,
                "privacy_attack_files": 0,
                "rating_files": 0,
                "env_files": 0,
                "options_file_exists": False
            }
            
            # Count files per persona
            for persona_id in config.supported_personas:
                files = [
                    self.file_resolver.get_security_attacks_file(config, persona_id),
                    self.file_resolver.get_privacy_attacks_file(config, persona_id),
                    self.file_resolver.get_ratings_file(config, persona_id),
                    self.file_resolver.get_env_file(config, persona_id)
                ]
                
                for i, file_path in enumerate(files):
                    if os.path.exists(file_path):
                        use_case_richness["total_files"] += 1
                        if i == 0:
                            use_case_richness["security_attack_files"] += 1
                        elif i == 1:
                            use_case_richness["privacy_attack_files"] += 1
                        elif i == 2:
                            use_case_richness["rating_files"] += 1
                        elif i == 3:
                            use_case_richness["env_files"] += 1
            
            # Check options file
            options_file = self.file_resolver.get_options_file(config)
            use_case_richness["options_file_exists"] = os.path.exists(options_file)
            
            stats["file_counts"][use_case_name] = use_case_richness
        
        return stats
    
    def _calculate_complexity_metrics(self) -> Dict[str, Any]:
        """Calculate benchmark complexity metrics"""
        stats = {
            "avg_attacks_per_persona": 0,
            "total_attack_scenarios": 0,
            "complexity_distribution": {},
            "evaluation_criteria_count": 0
        }
        
        total_attacks = 0
        total_personas = 0
        
        for use_case_name in self.registry.list_use_cases():
            config = self.registry.get_use_case(use_case_name)
            if not config:
                continue
                
            for persona_id in config.supported_personas:
                total_personas += 1
                persona_attacks = 0
                
                # Count security attacks
                sec_file = self.file_resolver.get_security_attacks_file(config, persona_id)
                if os.path.exists(sec_file):
                    persona_attacks += self._count_attacks_in_file(sec_file, "security_attacks")
                
                # Count privacy attacks
                priv_file = self.file_resolver.get_privacy_attacks_file(config, persona_id)
                if os.path.exists(priv_file):
                    persona_attacks += self._count_attacks_in_file(priv_file, "categories")
                
                total_attacks += persona_attacks
        
        stats["avg_attacks_per_persona"] = total_attacks / total_personas if total_personas else 0
        stats["total_attack_scenarios"] = total_attacks
        
        return stats
    
    def _count_attacks_in_file(self, file_path: str, root_key: str) -> int:
        """Count the number of attacks in a JSON file"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                root_data = data.get(root_key, {})
                
                count = 0
                if root_key == "security_attacks":
                    for category, attacks in root_data.items():
                        count += len(attacks)
                elif root_key == "categories":
                    for category, category_data in root_data.items():
                        # Check for items structure (direct list)
                        if "items" in category_data:
                            count += len(category_data["items"])
                        # Check for attacks structure (nested dict)
                        elif "attacks" in category_data:
                            count += len(category_data["attacks"])
                
                return count
        except Exception:
            return 0
    
    def _generate_overall_summary(self, use_case_stats, attack_stats, persona_stats, 
                                data_richness, complexity_metrics) -> Dict[str, Any]:
        """Generate overall benchmark summary"""
        return {
            "benchmark_name": "ConVerse Benchmark",
            "total_use_cases": use_case_stats["total_count"],
            "total_domains": len(use_case_stats["domains"]),
            "total_attacks": attack_stats["total_attacks"],
            "total_security_attacks": attack_stats["security_attacks"]["total_count"],
            "total_privacy_attacks": attack_stats["privacy_attacks"]["total_count"],
            "total_personas": persona_stats["total_unique_personas"],
            "avg_attacks_per_persona": round(complexity_metrics["avg_attacks_per_persona"], 2),
            "supported_domains": use_case_stats["domains"],
            "attack_categories": {
                "security": len(attack_stats["security_attacks"]["categories"]),
                "privacy": len(attack_stats["privacy_attacks"]["data_categories"])
            },
            "complexity_level": self._assess_complexity_level(complexity_metrics, attack_stats)
        }
    
    def _assess_complexity_level(self, complexity_metrics, attack_stats) -> str:
        """Assess overall benchmark complexity level"""
        avg_attacks = complexity_metrics["avg_attacks_per_persona"]
        total_categories = (
            len(attack_stats["security_attacks"]["categories"]) +
            len(attack_stats["privacy_attacks"]["data_categories"])
        )
        
        if avg_attacks > 20 and total_categories > 15:
            return "High"
        elif avg_attacks > 10 and total_categories > 8:
            return "Medium"
        else:
            return "Low"


def format_stats_report(stats: BenchmarkStats) -> str:
    """Format benchmark statistics into a comprehensive report"""
    report = []
    report.append("=" * 80)
    report.append("🎯 ConVerse BENCHMARK STATISTICS REPORT")
    report.append("=" * 80)
    report.append("")
    
    # Overall Summary
    summary = stats.overall_summary
    report.append("📊 OVERALL SUMMARY")
    report.append("-" * 40)
    report.append(f"Benchmark Name: {summary['benchmark_name']}")
    report.append(f"Total Use Cases: {summary['total_use_cases']}")
    report.append(f"Supported Domains: {', '.join(summary['supported_domains'])}")
    report.append(f"Total Personas: {summary['total_personas']}")
    report.append(f"Total Attack Scenarios: {summary['total_attacks']}")
    report.append(f"  - Security Attacks: {summary['total_security_attacks']}")
    report.append(f"  - Privacy Attacks: {summary['total_privacy_attacks']}")
    report.append(f"Average Attacks per Persona: {summary['avg_attacks_per_persona']}")
    report.append(f"Complexity Level: {summary['complexity_level']}")
    report.append("")
    
    # Use Case Details
    report.append("🏢 USE CASE ANALYSIS")
    report.append("-" * 40)
    for use_case, details in stats.use_case_stats["use_case_details"].items():
        report.append(f"📋 {use_case.upper().replace('_', ' ')}")
        report.append(f"   Description: {details['description']}")
        report.append(f"   Domain: {details['domain']}")
        report.append(f"   Agent Role: {details['external_agent_role']}")
        report.append(f"   Supported Personas: {details['supported_personas']}")
        report.append(f"   Available Options: {details['options_count']}")
        report.append("")
    
    # Attack Statistics
    report.append("⚔️ ATTACK TYPE ANALYSIS")
    report.append("-" * 40)
    
    # Security Attacks
    sec_stats = stats.attack_stats["security_attacks"]
    report.append(f"🔒 Security Attacks: {sec_stats['total_count']} total")
    report.append(f"   Categories: {', '.join(sec_stats['categories'])}")
    report.append(f"   Responsibility Flags:")
    for flag, count in sec_stats["responsibility_flags"].items():
        report.append(f"      - {flag}: {count}")
    report.append(f"   Harm Levels:")
    for level, count in sec_stats["harm_levels"].items():
        report.append(f"      - {level}: {count}")
    report.append("")
    
    # Privacy Attacks
    priv_stats = stats.attack_stats["privacy_attacks"]
    report.append(f"🔐 Privacy Attacks: {priv_stats['total_count']} total")
    report.append(f"   Data Categories: {', '.join(priv_stats['data_categories'])}")
    report.append(f"   Information Types: {len(priv_stats['information_types'])} unique types")
    if priv_stats['privacy_levels']:
        report.append(f"   Privacy Levels:")
        for level, count in priv_stats["privacy_levels"].items():
            report.append(f"      - {level}: {count}")
    report.append(f"   Leak Types:")
    for leak_type, count in priv_stats["leak_types"].items():
        report.append(f"      - {leak_type}: {count}")
    report.append("")
    
    # Attack Distribution by Use Case
    report.append("📈 ATTACK DISTRIBUTION BY USE CASE")
    report.append("-" * 40)
    for use_case, distribution in stats.attack_stats["attack_distribution"].items():
        report.append(f"{use_case}: Security={distribution['security']}, Privacy={distribution['privacy']}")
    report.append("")
    
    # Persona Analysis
    report.append("👥 PERSONA DIVERSITY")
    report.append("-" * 40)
    report.append(f"Total Unique Personas: {stats.persona_stats['total_unique_personas']}")
    report.append("Persona Details:")
    for persona_key, details in list(stats.persona_stats["persona_coverage"].items())[:5]:  # Show first 5
        report.append(f"   - {details['name']} ({details['use_case']} persona {details['persona_id']})")
        if details['profile_summary']:
            report.append(f"     {details['profile_summary'][:100]}...")
    if len(stats.persona_stats["persona_coverage"]) > 5:
        report.append(f"   ... and {len(stats.persona_stats['persona_coverage']) - 5} more personas")
    report.append("")
    
    # Data Richness
    report.append("💎 DATA RICHNESS METRICS")
    report.append("-" * 40)
    for use_case, richness in stats.data_richness["file_counts"].items():
        report.append(f"{use_case}:")
        report.append(f"   Total Files: {richness['total_files']}")
        report.append(f"   Security Attack Files: {richness['security_attack_files']}")
        report.append(f"   Privacy Attack Files: {richness['privacy_attack_files']}")
        report.append(f"   Rating Files: {richness['rating_files']}")
        report.append(f"   Environment Files: {richness['env_files']}")
        report.append(f"   Has Options File: {'Yes' if richness['options_file_exists'] else 'No'}")
        report.append("")
    
    report.append("=" * 80)
    return "\n".join(report)


def main():
    """Main function for running benchmark statistics"""
    parser = argparse.ArgumentParser(description="Generate ConVerse Benchmark Statistics")
    parser.add_argument("--output", "-o", type=str, help="Output file for statistics report")
    parser.add_argument("--json", action="store_true", help="Output statistics in JSON format")
    parser.add_argument("--base-path", type=str, default="", help="Base path for benchmark files")
    
    args = parser.parse_args()
    
    # Initialize analyzer
    analyzer = BenchmarkAnalyzer(base_path=args.base_path)
    
    # Analyze benchmark
    stats = analyzer.analyze_benchmark()
    
    if args.json:
        # Output as JSON
        output_data = {
            "use_case_stats": stats.use_case_stats,
            "attack_stats": stats.attack_stats,
            "persona_stats": stats.persona_stats,
            "data_richness": stats.data_richness,
            "complexity_metrics": stats.complexity_metrics,
            "overall_summary": stats.overall_summary
        }
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2, default=str)
            print(f"📄 Statistics saved to {args.output}")
        else:
            print(json.dumps(output_data, indent=2, default=str))
    else:
        # Output as formatted report
        report = format_stats_report(stats)
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"📄 Report saved to {args.output}")
        else:
            print(report)


if __name__ == "__main__":
    main()
