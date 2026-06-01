"""
Python数据处理与自动化脚本模板 - 高频接单需求
用途：Excel批量处理、文件自动化、数据清洗、报表生成
作者：Python接单工具包 | 2026-05
"""

import pandas as pd
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Union
import shutil
import json
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class ExcelProcessor:
    """
    Excel/CSV 数据处理类 - 最常见的接单需求之一
    客户场景：合并多个表格、数据清洗、格式转换、公式计算
    """

    def __init__(self, input_dir: str = 'input', output_dir: str = 'output'):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_excel(self, filepath: str, sheet_name: Union[str, int] = 0, **kwargs) -> pd.DataFrame:
        """加载Excel文件"""
        path = Path(filepath)
        if not path.is_absolute():
            path = self.input_dir / path
        
        logger.info(f"📂 加载文件: {path.name}")
        
        # 自动检测编码和格式
        if path.suffix.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(path, sheet_name=sheet_name, **kwargs)
        elif path.suffix.lower() == '.csv':
            # 尝试多种编码
            for encoding in ['utf-8-sig', 'gbk', 'gb2312', 'utf-8']:
                try:
                    df = pd.read_csv(path, encoding=encoding, **kwargs)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError(f"无法解码文件: {path}")
        else:
            raise ValueError(f"不支持的文件格式: {path.suffix}")
        
        logger.info(f"   ✅ 加载成功: {len(df)} 行 × {len(df.columns)} 列")
        return df

    def merge_multiple_files(
        self,
        file_pattern: str = '*.xlsx',
        output_filename: str = None,
        remove_duplicates: bool = True,
        **read_kwargs
    ) -> pd.DataFrame:
        """
        合并多个Excel/CSV文件（高频需求）
        
        Args:
            file_pattern: 文件匹配模式 (如 '*.xlsx', 'sales_*.csv')
            output_filename: 输出文件名
            remove_duplicates: 是否去重
        
        Returns:
            合并后的DataFrame
        """
        all_files = list(self.input_dir.glob(file_pattern))
        
        if not all_files:
            logger.warning(f"⚠️  在 {self.input_dir} 中未找到匹配 {file_pattern} 的文件")
            return pd.DataFrame()
        
        logger.info(f"📁 找到 {len(all_files)} 个文件待合并")
        
        dfs = []
        for file_path in sorted(all_files):
            try:
                df = self.load_excel(file_path, **read_kwargs)
                # 添加来源列，方便追溯
                df['数据来源'] = file_path.stem
                dfs.append(df)
            except Exception as e:
                logger.error(f"   ❌ 加载失败 {file_path.name}: {e}")
        
        if not dfs:
            return pd.DataFrame()
        
        # 合并所有DataFrame
        merged = pd.concat(dfs, ignore_index=True)
        
        if remove_duplicates and len(merged) > 0:
            before_count = len(merged)
            merged = merged.drop_duplicates()
            removed = before_count - len(merged)
            if removed > 0:
                logger.info(f"   🗑️  已去重: 移除 {removed} 条重复记录")
        
        logger.info(f"✅ 合并完成: 共 {len(merged)} 条记录")
        
        # 保存结果
        if output_filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"合并数据_{timestamp}.xlsx"
        
        output_path = self.output_dir / output_filename
        merged.to_excel(output_path, index=False, engine='openpyxl')
        logger.info(f"💾 已保存: {output_path}")
        
        return merged

    def clean_data(
        self,
        df: pd.DataFrame,
        columns_to_clean: Optional[List[str]] = None,
        fill_na_value: str = '',
        strip_whitespace: bool = True,
        standardize_dates: bool = True,
        date_columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        数据清洗（客户最常需要的服务）
        
        功能：
        - 去除空格
        - 填充空值
        - 标准化日期格式
        - 统一文本格式
        """
        result = df.copy()
        cleaned_cols = columns_to_clean or df.columns.tolist()
        
        logger.info(f"🧹 开始数据清洗...")
        
        for col in cleaned_cols:
            if col not in result.columns:
                continue
            
            if strip_whitespace and result[col].dtype == 'object':
                # 去除首尾空格
                result[col] = result[col].str.strip()
                # 合并多余空格
                result[col] = result[col].str.replace(r'\s+', ' ', regex=True)
            
            # 填充空值
            if result[col].isna().any():
                na_count = result[col].isna().sum()
                result[col] = result[col].fillna(fill_na_value)
                logger.info(f'   ✅ 列 "{col}": 填充了 {na_count} 个空值')
        
        # 标准化日期格式
        if standardize_dates and date_columns:
            for col in date_columns:
                if col in result.columns:
                    try:
                        result[col] = pd.to_datetime(result[col], errors='coerce').dt.strftime('%Y-%m-%d')
                        logger.info(f'   📅 日期列 "{col}" 已标准化')
                    except Exception as e:
                        logger.warning(f'   ⚠️ 日期格式化失败 "{col}": {e}')
        
        logger.info(f"✅ 清洗完成")
        return result


class FileAutomationTool:
    """
    文件自动化处理工具 - 另一个高频需求
    用途：批量重命名、文件整理、自动分类、备份归档
    """

    def __init__(self, work_dir: str = '.'):
        self.work_dir = Path(work_dir)

    def batch_rename(
        self,
        source_dir: str,
        pattern: str = '*',
        naming_rule: str = '{date}_{name}{ext}',
        dry_run: bool = False,
    ) -> List[Dict]:
        """
        批量重命名文件
        
        Args:
            source_dir: 源目录
            pattern: 文件匹配模式
            naming_rule: 命名规则模板
                      支持变量: {date}, {name}, {ext}, {index}
            dry_run: 仅预览不执行
        
        Returns:
            重命名操作列表
        """
        source_path = self.work_dir / source_dir
        files = sorted(source_path.glob(pattern))
        
        operations = []
        today = datetime.now().strftime('%Y%m%d')
        
        for idx, old_file in enumerate(files, 1):
            if old_file.is_file():
                # 构建新文件名
                new_name = naming_rule.format(
                    date=today,
                    name=old_file.stem,
                    ext=old_file.suffix,
                    index=str(idx).zfill(3),
                )
                
                new_file = old_file.parent / new_name
                
                operation = {
                    '原文件': old_file.name,
                    '新文件': new_name,
                    '状态': '待执行',
                }
                
                if not dry_run:
                    try:
                        old_file.rename(new_file)
                        operation['状态'] = '✅ 完成'
                        logger.info(f"   重命名: {old_file.name} → {new_file.name}")
                    except Exception as e:
                        operation['状态'] = f'❌ 失败: {e}'
                        logger.error(f"   失败: {old_file.name}: {e}")
                else:
                    operation['状态'] = '预览'
                
                operations.append(operation)
        
        logger.info(f"\n{'='*50}")
        logger.info(f"📋 批量重命名 {'预览' if dry_run else '执行'} 结果:")
        logger.info(f"{'='*50}")
        for op in operations:
            logger.info(f"  {op['原文件']:<30} → {op['新文件'].name:<30} [{op['状态']}]")
        
        return operations

    def organize_by_type(
        self,
        source_dir: str,
        target_dir: str = 'sorted_files',
        move_or_copy: str = 'copy',
    ) -> Dict[str, int]:
        """
        按文件类型自动分类整理
        
        Args:
            source_dir: 源目录
            target_dir: 目标目录
            move_or_copy: 'move'移动 或 'copy'复制
        
        Returns:
            各类型文件数量统计
        """
        source_path = self.work_dir / source_dir
        target_path = self.work_dir / target_dir
        target_path.mkdir(parents=True, exist_ok=True)
        
        # 文件类型映射
        type_mapping = {
            '图片': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'],
            '文档': ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'],
            '视频': ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'],
            '音频': ['.mp3', '.wav', '.flac', '.aac', '.ogg'],
            '压缩包': ['.zip', '.rar', '.7z', '.tar', '.gz'],
            '代码': ['.py', '.js', '.java', '.cpp', '.html', '.css', '.json', '.xml'],
            '其他': [],
        }
        
        stats = {}
        files = [f for f in source_path.iterdir() if f.is_file()]
        
        logger.info(f"📂 开始整理 {len(files)} 个文件...")
        
        for file_path in files:
            # 确定文件类型
            ext = file_path.suffix.lower()
            file_type = '其他'
            
            for type_name, extensions in type_mapping.items():
                if ext in extensions:
                    file_type = type_name
                    break
            
            # 创建类型子目录
            type_dir = target_path / file_type
            type_dir.mkdir(exist_ok=True)
            
            # 移动或复制
            dest = type_dir / file_path.name
            try:
                if move_or_copy == 'move':
                    shutil.move(str(file_path), str(dest))
                else:
                    shutil.copy2(str(file_path), str(dest))
                
                stats[file_type] = stats.get(file_type, 0) + 1
                
            except Exception as e:
                logger.error(f"   ❌ 处理失败 {file_path.name}: {e}")
        
        # 输出统计
        logger.info(f"\n{'='*50}")
        logger.info(f"📊 整理完成统计:")
        logger.info(f"{'='*50}")
        total = 0
        for ftype, count in sorted(stats.items()):
            logger.info(f"  {ftype:<10}: {count:>5} 个文件")
            total += count
        logger.info(f"  {'总计':<10}: {total:>5} 个文件")
        logger.info(f"💾 输出目录: {target_path.absolute()}")
        
        return stats


class ReportGenerator:
    """报表生成器 - 数据分析后的可视化输出"""

    @staticmethod
    def create_summary_report(
        df: pd.DataFrame,
        group_by_column: str,
        value_column: str,
        aggregation: str = 'sum',
        output_filename: str = None,
    ) -> pd.DataFrame:
        """
        生成分组汇总报表（非常实用的功能）
        
        Args:
            df: 源数据
            group_by_column: 分组依据的列名
            value_column: 要聚合的数值列
            aggregation: 聚合方式 ('sum', 'mean', 'count', 'max', 'min')
        
        Returns:
            汇总报表DataFrame
        """
        agg_funcs = {
            'sum': '求和',
            'mean': '平均值',
            'count': '计数',
            'max': '最大值',
            'min': '最小值',
        }
        
        if value_column not in df.columns:
            raise ValueError(f"列 '{value_column}' 不存在")
        if group_by_column not in df.columns:
            raise ValueError(f"列 '{group_by_column}' 不存在")
        
        logger.info(f"📊 生成汇总报表: 按 [{group_by_column}] 分组，[{value_column}] {agg_funcs.get(aggregation, aggregation)}")
        
        agg_func_map = {
            'sum': 'sum',
            'mean': 'mean',
            'count': 'count',
            'max': 'max',
            'min': 'min',
        }
        
        report = df.groupby(group_by_column)[value_column].agg(agg_func_map.get(aggregation, 'sum')).reset_index()
        report.columns = [group_by_column, f'{value_column}_{aggregation}']
        
        # 排序
        report = report.sort_values(by=report.columns[-1], ascending=False)
        
        # 保存
        if output_filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"汇总报表_{timestamp}.xlsx"
        
        output_path = Path('output') / output_filename
        output_path.parent.mkdir(exist_ok=True)
        
        # 同时保存为Excel和CSV方便客户使用
        report.to_excel(output_path, index=False, engine='openpyxl')
        report.to_csv(output_path.with_suffix('.csv'), index=False, encoding='utf-8-sig')
        
        logger.info(f"💾 报表已保存:\n   Excel: {output_path}\n   CSV: {output_path.with_suffix('.csv')}")
        
        # 打印预览
        print("\n" + "=" * 60)
        print(f"  📈 {group_by_column} - {value_column} {agg_funcs.get(aggregation, aggregation)} 报表")
        print("=" * 60)
        print(report.to_string(index=False))
        print("=" * 60)
        
        return report


def main():
    """
    使用示例 - 展示所有功能的用法
    实际接单时根据客户需求选择对应功能即可
    """
    
    print("=" * 60)
    print("  Python数据处理工具包 - 接单专用")
    print("  支持功能：")
    print("    1. 多文件合并")
    print("    2. 数据清洗")
    print("    3. 批量重命名")
    print("    4. 文件分类整理")
    print("    5. 报表生成")
    print("=" * 60)
    
    # ===== 示例1：合并多个Excel文件 =====
    print("\n\n【示例1】合并多个Excel文件")
    processor = ExcelProcessor('input', 'output')
    
    # 创建测试数据（实际使用时删除这部分）
    test_dir = Path('input')
    test_dir.mkdir(exist_ok=True)
    for i in range(1, 4):
        test_df = pd.DataFrame({
            '产品名称': [f'产品{i}-{j}' for j in range(1, 6)],
            '价格': [100 + i * j for j in range(1, 6)],
            '销量': [10 + i * j for j in range(1, 6)],
        })
        test_df.to_excel(test_dir / f'sales_2024_0{i}.xlsx', index=False)
    
    merged_df = processor.merge_multiple_files(
        file_pattern='sales_*.xlsx',
        output_filename='销售数据合并.xlsx'
    )
    
    if not merged_df.empty:
        # ===== 示例2：数据清洗 =====
        print("\n\n【示例2】数据清洗")
        clean_df = processor.clean_data(
            merged_df,
            fill_na_value='0',
            strip_whitespace=True,
        )
        
        # ===== 示例3：生成汇总报表 =====
        print("\n\n【示例3】生成汇总报表")
        report = ReportGenerator.create_summary_report(
            df=clean_df,
            group_by_column='产品名称',
            value_column='价格',
            aggregation='sum'
        )


if __name__ == '__main__':
    main()
