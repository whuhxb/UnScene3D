import lib.models.encoders_2d.lseg as lseg
# import lib.models.encoders_2d.densecl as denscl
import lib.models.encoders_2d.dino as dino

MODELS = []

def add_models(module):
  MODELS.extend([getattr(module, a) for a in dir(module) if 'Net' in a])

add_models(lseg)
# add_models(denscl)
add_models(dino)

def get_models():
  '''Returns a tuple of sample models.'''
  return MODELS

def load_2d_model(name):
  '''Creates and returns an instance of the model given its class name.
  '''
  # Find the model class from its name
  all_models = get_models()
  mdict = {model.__name__: model for model in all_models}
  if name not in mdict:
    print('Invalid model index. Options are:')
    # Display a list of valid model names
    for model in all_models:
      print('\t* {}'.format(model.__name__))
    return None
  NetClass = mdict[name]

  return NetClass