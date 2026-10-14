import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_reference_identity_repair import line,page,index
from pdf_rules.model import Label
from pdf_rules.reference_identity_repair import repair_reference_identity
from pdf_rules.local_rules import detect_rules


class ExperimentContextIsolationTests(unittest.TestCase):
 def fixture(self,combined=False,parent_dataset=False):
  caption=line('表5.4 Mini-ImageNet数据集上的方法性能比较',120,page=2,bold=True,size=10);header=line('METHODS 5-way 1-shot ACC 5-way 5-shot ACC',155,page=2,role='table');base=line('Vanilla GL-ViT 88.04 96.45',185,page=2,role='table');row=line('HP-GP + GL-ViT (RBF) 89.25 97.01',215,page=2,role='table')
  metadata='Mini-ImageNet数据集包含'+('ImageNet数据集中的' if parent_dataset else '')+'100个类别，每类600张图像。'
  configuration=('' if parent_dataset else '在另一个MNIST数据集实验中，')+'本实验将HP-GP应用于视觉Transformer的MLP第一层，采用RBF核函数。'
  pre=line(metadata+(configuration if combined or parent_dataset else ''),60,page=1 if not combined and not parent_dataset else 2)
  config=line(configuration,500,page=2);result=line('实验结果表明，将HP-GP应用于MLP或卷积层时，性能显著提升。',600,page=2)
  if combined or parent_dataset:pages=(page(pre,caption,header,base,row,result,number=2,tables=((80,145,520,240),)),)
  else:pages=(page(pre,number=1),page(caption,header,base,row,config,result,number=2,tables=((80,145,520,240),)))
  return repair_reference_identity(index(*pages,tables=[Label('5.4',caption,'body')]))
 def test_other_experiment_cannot_borrow_dataset_metadata_from_neighbor_page(self):
  self.assertEqual(len(detect_rules(self.fixture(),{16})['16']['findings']),1)
 def test_other_explicit_dataset_in_same_context_cannot_borrow_prior_metadata(self):
  self.assertEqual(len(detect_rules(self.fixture(combined=True),{16})['16']['findings']),1)
 def test_parent_dataset_in_a_subset_definition_is_not_a_new_experiment(self):
  self.assertFalse(detect_rules(self.fixture(parent_dataset=True),{16})['16']['findings'])


class DistinctTaskVariantTests(unittest.TestCase):
 def fixture(self,exact=True,second_task=True):
  a=line('表4.2 分子描述生成任务表现',120,page=2,bold=True,size=10);ha=line('Model BLEU ROUGE METEOR',155,page=2,role='table');xa=line('Ours(CheBI-20) 57.3 70.7 67.7',185,page=2,role='table');ya=line('Ours* 48.5 55.4 46.8',215,page=2,role='table')
  b=line('表4.3 基于文本的分子序列生成任务表现',120,page=3,bold=True,size=10);hb=line('Model BLEU '+('EXACT LEVENSHTEIN' if exact else 'ROUGE METEOR'),155,page=3,role='table');xb=line('Ours(CheBI-20) 86.3 38.9 13.8',185,page=3,role='table');yb=line('Ours* 87.9 37.5 11.3',215,page=3,role='table')
  pre=line('将实验分两个部分，训练测试标记为“CheBI-20”；第二个自组织数据集训练测试标记为“*”。',60,page=2)
  first=line('在分子描述生成任务中，我们的模型与其他模型表现相近，BLEU指标没有明显区别。',500,page=2)
  second=line('在基于文本描述的分子生成任务中，我们观察到：模型采用仅Transformer解码器的自回归结构，SMILES表示时EXACT相较编码器解码器模型明显下降。' if second_task else '基于文本描述可以生成分子，其解码算法处理SMILES。',530,page=2)
  return repair_reference_identity(index(page(pre,a,ha,xa,ya,first,second,number=2,tables=((80,145,520,240),)),page(b,hb,xb,yb,number=3,tables=((80,145,520,240),)),tables=[Label('4.2',a,'body'),Label('4.3',b,'body')]))
 def test_two_task_paragraphs_bind_their_separate_physical_metric_tables(self):
  self.assertFalse(detect_rules(self.fixture(),{16})['16']['findings'])
 def test_second_task_cannot_borrow_metric_missing_from_its_actual_table(self):
  self.assertEqual([f['token'] for f in detect_rules(self.fixture(exact=False),{16})['16']['findings']],['4.3'])
 def test_first_task_metric_cannot_credit_second_task_from_topic_words(self):
  self.assertEqual([f['token'] for f in detect_rules(self.fixture(second_task=False),{16})['16']['findings']],['4.3'])
