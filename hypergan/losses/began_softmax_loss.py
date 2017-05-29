import tensorflow as tf
from hypergan.util.ops import *
from hypergan.util.hc_tf import *
import hyperchamber as hc
from hypergan.generators.resize_conv_generator import minmaxzero
from hypergan.losses.common import *

def config(
        reduce=tf.reduce_mean, 
        reverse=False,
        discriminator=None,
        alignment_lambda=[1],
        k_lambda=0.01,
        labels=[[0,-1,-1]],
        initial_k=0,
        gradient_penalty=False,
        use_k=[True],
        include_recdistance=False,
        include_recdistance2=False,
        include_grecdistance=False,
        include_grecdistance2=False,
        include_distance=False,
        gamma=0.75):
    selector = hc.Selector()
    selector.set("reduce", reduce)
    selector.set('reverse', reverse)
    selector.set('discriminator', discriminator)

    selector.set('create', create)
    selector.set('k_lambda', k_lambda)
    selector.set('initial_k', initial_k)
    selector.set('gradient_penalty',gradient_penalty)

    selector.set('labels', labels)
    selector.set('type', ['wgan', 'lsgan'])
    selector.set('use_k', use_k)
    selector.set('gamma', gamma)

    if include_recdistance:
        selector.set('include_recdistance', True)
    if include_recdistance2:
        selector.set('include_recdistance2', True)
    if include_grecdistance:
        selector.set('include_grecdistance', True)
    if include_grecdistance2:
        selector.set('include_grecdistance2', True)
    if include_distance:
        selector.set('include_distance', True)
    return selector.random_config()

def g(gan, z):
    #reuse variables
    with(tf.variable_scope("generator", reuse=True)):
        # call generator
        generator = hc.Config(hc.lookup_functions(gan.config.generator))
        nets = generator.create(generator, gan, z)
        return nets[0]

def loss(gan, x, reuse=True):
    for i, discriminator in enumerate(gan.config.discriminators):
        discriminator = hc.Config(hc.lookup_functions(discriminator))
        with(tf.variable_scope("discriminator", reuse=reuse)):
            ds = discriminator.create(gan, discriminator, x, x, gan.graph.xs, gan.graph.gs,prefix="d_"+str(i))
            bs = gan.config.batch_size
            net = ds
            net = tf.slice(net, [0,0],[bs, -1])
            print('net is', net)
            return tf.reduce_mean(net, axis=1)

def dist(x1, x2):
    bs = int(x1.get_shape()[0])
    return tf.reshape(tf.abs(x1 - x2), [bs, -1])

# boundary equilibrium gan
def began(gan, config, d_real, d_fake, prefix=''):
    a,b,c = config.labels
    d_fake = config.reduce(d_fake, axis=1)
    d_real = config.reduce(d_real, axis=1)

    k = tf.get_variable(prefix+'k', [1], initializer=tf.constant_initializer(config.initial_k), dtype=config.dtype)

    ln_zb = tf.reduce_sum(tf.exp(-d_real))+tf.reduce_sum(tf.exp(-d_fake))
    ln_zb = tf.log(ln_zb)
    l_x = tf.reduce_mean(d_real) + ln_zb
    g_loss = tf.reduce_mean(d_fake) + tf.reduce_mean(d_real) + ln_zb
    l_dg =-tf.reduce_mean(d_fake)-tf.reduce_mean(d_real)

    if config.use_k:
        d_loss = l_x+k*l_dg
    else:
        d_loss = l_x+l_dg

    if config.gradient_penalty:
        d_loss += gradient_penalty(gan, config.gradient_penalty)

    gamma = config.gamma * tf.ones_like(d_fake)

    if config.use_k:
        gamma_d_real = gamma*d_real
    else:
        gamma_d_real = d_real
    k_loss = tf.reduce_mean(gamma_d_real - d_fake, axis=0)
    update_k = tf.assign(k, k + config.k_lambda * k_loss)
    measure = tf.reduce_mean(l_x) + tf.abs(k_loss)

    d_loss = tf.reduce_mean(d_loss)
    g_loss = tf.reduce_mean(g_loss)


    if 'include_recdistance' in config:
        reconstruction = tf.add_n([
            dist(gan.graph.rxabba, gan.graph.rxa),
            dist(gan.graph.rxbaab, gan.graph.rxb)
            ])
        reconstruction *= config.alignment_lambda
        g_loss += tf.reduce_mean(reconstruction)

    if 'include_recdistance2' in config:
        reconstruction = tf.add_n([
            dist(gan.graph.rxabba, gan.graph.xa),
            dist(gan.graph.rxbaab, gan.graph.xb)
            ])
        reconstruction *= config.alignment_lambda
        g_loss += tf.reduce_mean(reconstruction)


    if 'include_grecdistance' in config:
        reconstruction = tf.add_n([
            dist(gan.graph.rgabba, gan.graph.rga),
            dist(gan.graph.rgbaab, gan.graph.rgb)
            ])
        reconstruction *= config.alignment_lambda
        g_loss += tf.reduce_mean(reconstruction)

    if 'include_grecdistance2' in config:
        reconstruction = tf.add_n([
            dist(gan.graph.rgabba, gan.graph.ga),
            dist(gan.graph.rgbaab, gan.graph.gb)
            ])
        reconstruction *= config.alignment_lambda
        g_loss += tf.reduce_mean(reconstruction)


    if 'include_distance' in config:
        reconstruction = tf.add_n([
            dist(gan.graph.xabba, gan.graph.xa),
            dist(gan.graph.xbaab, gan.graph.xb)
            ])
        reconstruction *= config.alignment_lambda
        g_loss += tf.reduce_mean(reconstruction)
        print("- - - -- - Reconstruction loss added.")

    return [k, update_k, measure, d_loss, g_loss]


def create(config, gan):
    x = gan.graph.x
    if(config.discriminator == None):
        d_real = gan.graph.d_real
        d_fake = gan.graph.d_fake
    else:
        d_real = gan.graph.d_reals[config.discriminator]
        d_fake = gan.graph.d_fakes[config.discriminator]
    k, update_k, measure, d_loss, g_loss = began(gan, config, d_real, d_fake)
    gan.graph.measure = measure
    gan.graph.k = k
    gan.graph.update_k = update_k

    gan.graph.gamma = config.gamma


    return [d_loss, g_loss]
